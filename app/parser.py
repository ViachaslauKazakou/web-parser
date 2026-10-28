import asyncio
import ipaddress
import logging
import socket
from datetime import datetime, timezone
from urllib.parse import quote, urlencode, urljoin, urlsplit

from bs4 import BeautifulSoup
from playwright.async_api import Browser, BrowserContext, Page, TimeoutError as PlaywrightTimeoutError, async_playwright

from app.config import get_settings

logger = logging.getLogger(__name__)
_PARSER_SEMAPHORE = asyncio.Semaphore(1)
DISABLE_WEBRTC_INIT_SCRIPT = """
for (const api of ["RTCPeerConnection", "webkitRTCPeerConnection"]) {
  try {
    Object.defineProperty(globalThis, api, {
      value: undefined,
      writable: false,
      configurable: false,
    });
  } catch (_) {
    try { globalThis[api] = undefined; } catch (_ignored) {}
  }
}
"""


class ParserInputError(ValueError):
    """Invalid or disallowed parser input."""


class ParserFailure(RuntimeError):
    """A remote forum could not be parsed."""


class EgressTransferLimitExceeded(RuntimeError):
    pass


def host_is_allowed(hostname: str, allowed_hosts: tuple[str, ...]) -> bool:
    normalized = hostname.lower().rstrip(".")
    return any(normalized == host or normalized.endswith(f".{host}") for host in allowed_hosts)


def validate_topic_url_syntax(url: str, allowed_hosts: tuple[str, ...]) -> str:
    try:
        parsed = urlsplit(url.strip())
        hostname = (parsed.hostname or "").lower().rstrip(".")
        port = parsed.port
    except ValueError as exc:
        raise ParserInputError("Некорректный URL темы.") from exc
    if parsed.scheme.lower() != "https":
        raise ParserInputError("Разрешены только HTTPS-ссылки на форум.")
    if not hostname or parsed.username or parsed.password:
        raise ParserInputError("В ссылке должен быть публичный адрес форума без учётных данных.")
    if port not in (None, 443):
        raise ParserInputError("Нестандартные порты для парсинга запрещены.")
    if not host_is_allowed(hostname, allowed_hosts):
        raise ParserInputError("Домен не входит в PARSER_ALLOWED_HOSTS.")
    return hostname


async def _assert_public_host(hostname: str) -> None:
    await _resolve_public_addresses(hostname, 443)


async def _resolve_public_addresses(hostname: str, port: int) -> list[str]:
    """Resolve once, reject non-public answers, and return IPs safe to pin to."""
    try:
        infos = await asyncio.to_thread(socket.getaddrinfo, hostname, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ParserInputError("Не удалось определить публичный адрес домена форума.") from exc
    addresses = {str(info[4][0]).split("%", 1)[0] for info in infos}
    if not addresses:
        raise ParserInputError("Домен форума не имеет публичного адреса.")
    try:
        parsed_addresses = [ipaddress.ip_address(address) for address in addresses]
    except ValueError as exc:
        raise ParserInputError("Не удалось проверить адрес домена форума.") from exc
    if any(not address.is_global for address in parsed_addresses):
        raise ParserInputError("Запросы к локальным и внутренним адресам запрещены.")
    return sorted(addresses)


class SafeEgressProxy:
    """Tiny HTTPS CONNECT proxy that validates and pins every outbound hop.

    Chromium follows redirects internally, outside Playwright route handlers.
    The proxy sees every CONNECT (including redirects), checks the configured
    host allowlist, resolves public IPs, then connects to the resolved IP literal
    while TLS remains end-to-end between Chromium and the requested hostname.
    """

    def __init__(
        self,
        allowed_hosts: tuple[str, ...],
        *,
        max_request_bytes: int = 2 * 1024 * 1024,
        max_response_bytes: int = 8 * 1024 * 1024,
    ):
        self.allowed_hosts = allowed_hosts
        self.max_request_bytes = max_request_bytes
        self.max_response_bytes = max_response_bytes
        self._server: asyncio.AbstractServer | None = None

    @property
    def server_url(self) -> str:
        if not self._server or not self._server.sockets:
            raise RuntimeError("Egress proxy is not running")
        port = self._server.sockets[0].getsockname()[1]
        return f"http://127.0.0.1:{port}"

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0, limit=8192)

    async def close(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    @staticmethod
    def _parse_authority(authority: str) -> tuple[str, int] | None:
        try:
            parsed = urlsplit(f"//{authority}")
            host = (parsed.hostname or "").lower().rstrip(".")
            port = parsed.port
        except ValueError:
            return None
        if not host or parsed.username or parsed.password or port is None or parsed.path or parsed.query or parsed.fragment:
            return None
        return host, port

    @staticmethod
    async def _reply(writer: asyncio.StreamWriter, status_code: int, reason: str) -> None:
        writer.write(f"HTTP/1.1 {status_code} {reason}\r\nConnection: close\r\n\r\n".encode("ascii"))
        try:
            await writer.drain()
        except (ConnectionError, OSError):
            pass

    async def _handle(self, client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter) -> None:
        remote_writer: asyncio.StreamWriter | None = None
        try:
            request_line = await asyncio.wait_for(client_reader.readline(), timeout=5)
            header_size = len(request_line)
            while True:
                header = await asyncio.wait_for(client_reader.readline(), timeout=5)
                header_size += len(header)
                if header_size > 16 * 1024:
                    await self._reply(client_writer, 431, "Proxy Headers Too Large")
                    return
                if header in (b"\r\n", b"\n"):
                    break
                if not header:
                    await self._reply(client_writer, 400, "Incomplete Proxy Request")
                    return
            parts = request_line.decode("latin-1").strip().split()
            if len(parts) != 3 or parts[0].upper() != "CONNECT":
                await self._reply(client_writer, 405, "CONNECT Required")
                return
            destination = self._parse_authority(parts[1])
            if destination is None:
                await self._reply(client_writer, 400, "Invalid CONNECT Target")
                return
            hostname, port = destination
            if port != 443 or not host_is_allowed(hostname, self.allowed_hosts):
                await self._reply(client_writer, 403, "Destination Not Allowed")
                return

            addresses = await _resolve_public_addresses(hostname, port)
            for address in addresses:
                ip = ipaddress.ip_address(address)
                try:
                    remote_reader, remote_writer = await asyncio.wait_for(
                        asyncio.open_connection(
                            host=address,
                            port=port,
                            family=socket.AF_INET6 if ip.version == 6 else socket.AF_INET,
                        ),
                        timeout=10,
                    )
                    break
                except (OSError, TimeoutError):
                    continue
            else:
                await self._reply(client_writer, 502, "Destination Unavailable")
                return

            client_writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await client_writer.drain()
            await self._relay(
                client_reader,
                client_writer,
                remote_reader,
                remote_writer,
                max_request_bytes=self.max_request_bytes,
                max_response_bytes=self.max_response_bytes,
            )
        except ParserInputError:
            await self._reply(client_writer, 403, "Destination Not Allowed")
        except (asyncio.TimeoutError, UnicodeError, ConnectionError, OSError, ValueError):
            await self._reply(client_writer, 502, "Connection Rejected")
        finally:
            if remote_writer:
                remote_writer.close()
                try:
                    await remote_writer.wait_closed()
                except (ConnectionError, OSError):
                    pass
            client_writer.close()
            try:
                await client_writer.wait_closed()
            except (ConnectionError, OSError):
                pass

    @staticmethod
    async def _relay(
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
        remote_reader: asyncio.StreamReader,
        remote_writer: asyncio.StreamWriter,
        *,
        max_request_bytes: int,
        max_response_bytes: int,
    ) -> None:
        async def pump(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, byte_limit: int) -> None:
            transferred = 0
            try:
                while data := await reader.read(64 * 1024):
                    transferred += len(data)
                    if transferred > byte_limit:
                        raise EgressTransferLimitExceeded
                    writer.write(data)
                    await writer.drain()
            except (ConnectionError, OSError, EgressTransferLimitExceeded):
                pass

        tasks = {
            asyncio.create_task(pump(client_reader, remote_writer, max_request_bytes)),
            asyncio.create_task(pump(remote_reader, client_writer, max_response_bytes)),
        }
        _, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


class SearchEnginesParser:
    BASE_URL = "https://searchengines.guru"

    def __init__(self, allowed_hosts: tuple[str, ...] | None = None):
        self.allowed_hosts = allowed_hosts or get_settings().allowed_forum_hosts
        self._checked_hosts: set[str] = set()
        self.playwright = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self.proxy = SafeEgressProxy(self.allowed_hosts)
        self.max_page_chars = get_settings().max_parser_page_chars

    async def __aenter__(self) -> "SearchEnginesParser":
        await self._assert_allowed_host("searchengines.guru")
        try:
            await self.proxy.start()
            self.playwright = await async_playwright().start()
            args = [
                "--disable-dev-shm-usage",
                "--proxy-bypass-list=<-loopback>",
                "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
            ]
            self.browser = await self.playwright.chromium.launch(headless=True, chromium_sandbox=True, args=args)
            self.context = await self.browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1440, "height": 1000},
                locale="ru-RU",
                timezone_id="Europe/Moscow",
                proxy={"server": self.proxy.server_url, "bypass": "<-loopback>"},
                service_workers="block",
            )
            await self.context.add_init_script(DISABLE_WEBRTC_INIT_SCRIPT)
            await self.context.route("**/*", self._guard_request)
            self.page = await self.context.new_page()
            self.page.set_default_timeout(12_000)
            return self
        except BaseException:
            await self.close()
            raise

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        await self.close()

    async def close(self) -> None:
        if self.context:
            await self.context.close()
            self.context = None
        if self.browser:
            await self.browser.close()
            self.browser = None
        if self.playwright:
            await self.playwright.stop()
            self.playwright = None
        await self.proxy.close()

    async def _assert_allowed_host(self, hostname: str) -> None:
        hostname = hostname.lower().rstrip(".")
        if not host_is_allowed(hostname, self.allowed_hosts):
            raise ParserInputError("Домен не входит в PARSER_ALLOWED_HOSTS.")
        if hostname not in self._checked_hosts:
            await _assert_public_host(hostname)
            self._checked_hosts.add(hostname)

    async def _guard_request(self, route) -> None:
        request_url = urlsplit(route.request.url)
        hostname = request_url.hostname or ""
        try:
            if request_url.scheme != "https":
                await route.abort()
                return
            if route.request.resource_type in {"image", "media", "font"}:
                await route.abort()
                return
            await self._assert_allowed_host(hostname)
            await route.continue_()
        except ParserInputError:
            await route.abort()

    async def _bounded_page_content(self) -> str:
        markup = await self.page.content()
        if len(markup) > self.max_page_chars:
            raise ParserFailure(
                f"HTML страницы превышает безопасный лимит {self.max_page_chars:,} символов."
            )
        return markup

    async def _goto(self, url: str, *, wait_until: str = "domcontentloaded", timeout: int = 30_000):
        hostname = validate_topic_url_syntax(url, self.allowed_hosts)
        await self._assert_allowed_host(hostname)
        response = await self.page.goto(url, wait_until=wait_until, timeout=timeout)
        validate_topic_url_syntax(self.page.url, self.allowed_hosts)
        return response

    async def parse_user(
        self,
        username: str,
        *,
        by_id: bool = False,
        max_pages: int = 1,
        timeout_ms: int = 3000,
    ) -> dict:
        if by_id:
            if not username.isdecimal():
                raise ParserInputError("ID пользователя должен состоять только из цифр.")
            initial_url = f"{self.BASE_URL}/ru/users/{quote(username, safe='')}/comments"
            mode = "comments"
        else:
            initial_url = f"{self.BASE_URL}/ru/search?{urlencode({'keyword': username})}"
            mode = "keyword"

        messages: list[dict] = []
        seen: set[tuple[str, str, str]] = set()
        current_url = initial_url
        message_limit = get_settings().max_import_messages
        for page_number in range(1, max_pages + 1):
            try:
                response = await self._goto(current_url)
            except PlaywrightTimeoutError as exc:
                if page_number == 1:
                    raise ParserFailure("Форум не ответил вовремя. Уменьшите число страниц и повторите попытку.") from exc
                break
            if response and response.status >= 400:
                if page_number == 1:
                    raise ParserFailure(f"Форум вернул HTTP {response.status}.")
                break

            if len(messages) >= message_limit:
                break
            markup = await self._bounded_page_content()
            page_messages = await asyncio.to_thread(
                self._extract_user_page,
                markup,
                comments=by_id,
                limit=message_limit - len(messages),
            )
            for message in page_messages:
                key = (message.get("url", ""), message.get("date", ""), message.get("message", ""))
                if key not in seen:
                    seen.add(key)
                    messages.append(message)
                    if len(messages) >= message_limit:
                        break

            if len(messages) >= message_limit or page_number >= max_pages:
                break
            next_url = await asyncio.to_thread(self._next_page_url, markup, page_number + 1, self.page.url)
            if not next_url or next_url == current_url:
                break
            current_url = next_url
            await self.page.wait_for_timeout(timeout_ms)

        return {
            "user": username,
            "search_url": initial_url,
            "messages_count": len(messages),
            "messages": messages,
            "parsed_at": datetime.now(timezone.utc).isoformat(),
            "mode": mode,
            "error": "No messages found" if not messages else None,
            "warning": "Достигнут безопасный предел сообщений." if len(messages) >= message_limit else None,
        }

    async def parse_topic(self, url: str, *, max_messages: int = 50, max_pages: int = 20) -> dict:
        validate_topic_url_syntax(url, self.allowed_hosts)
        posts: list[dict] = []
        seen: set[tuple[str, str]] = set()
        current_url = url
        settings = get_settings()
        reply_limit = max_messages if max_messages > 0 else settings.max_import_messages
        total_post_limit = reply_limit + 1

        for page_number in range(1, max_pages + 1):
            try:
                response = await self._goto(current_url, wait_until="domcontentloaded", timeout=45_000)
            except PlaywrightTimeoutError as exc:
                if page_number == 1:
                    raise ParserFailure("Не удалось загрузить тему за отведённое время.") from exc
                break
            if response and response.status >= 400:
                if page_number == 1:
                    raise ParserFailure(f"Форум вернул HTTP {response.status}.")
                break

            if len(posts) >= total_post_limit:
                break
            markup = await self._bounded_page_content()
            page_posts = await asyncio.to_thread(
                self._extract_topic_posts,
                markup,
                limit=total_post_limit - len(posts),
            )
            for post in page_posts:
                if len(posts) >= total_post_limit:
                    break
                content = (post.get("content") or "").strip()
                author = (post.get("author") or "").strip()
                signature = (author, content)
                if content and signature not in seen:
                    posts.append(post)
                    seen.add(signature)

            reply_count = max(0, len(posts) - 1)
            if reply_count >= reply_limit or page_number >= max_pages:
                break
            next_url = await asyncio.to_thread(self._next_page_url, markup, page_number + 1, self.page.url)
            if not next_url or next_url == current_url:
                break
            current_url = next_url

        if not posts:
            raise ParserFailure("Не найдены сообщения темы: проверьте ссылку и доступность форума.")

        opener, replies = posts[0], posts[1:]
        if max_messages > 0:
            replies = replies[:max_messages]
        first_message = opener["content"]
        return {
            "title": opener.get("title") or "",
            "description": first_message[:300].rstrip() or None,
            "first_message": first_message,
            "messages": [
                {"external_id": f"reply-{index}", "author": post.get("author") or None, "content": post["content"]}
                for index, post in enumerate(replies, start=1)
                if post.get("content", "").strip()
            ],
            "source_url": self.page.url,
            "parsed_at": datetime.now(timezone.utc).isoformat(),
            "total_parsed": len(replies),
            "warning": (
                f"Достигнут безопасный предел {settings.max_import_messages} ответов."
                if max_messages == 0 and len(replies) >= settings.max_import_messages
                else None
            ),
        }

    @staticmethod
    def _parse_date(value: str | None) -> str:
        if value:
            try:
                parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed.isoformat()
            except ValueError:
                pass
            for date_format in ("%Y.%m.%d", "%d.%m.%Y", "%Y-%m-%d"):
                try:
                    return datetime.strptime(value.strip(), date_format).replace(tzinfo=timezone.utc).isoformat()
                except ValueError:
                    continue
        return datetime.now(timezone.utc).isoformat()

    @classmethod
    def _extract_user_page(cls, markup: str, *, comments: bool, limit: int | None = None) -> list[dict]:
        soup = BeautifulSoup(markup, "html.parser")
        results: list[dict] = []
        selectors = ".comments-list .comment" if comments else ".search-result__item"
        for item in soup.select(selectors, limit=limit):
            if comments:
                topic_link = item.select_one(".comment__topic a")
                message_el = item.select_one(".comment__content")
                time_el = item.select_one(".comment__date time")
                title = topic_link.get_text(" ", strip=True) if topic_link else "No title"
                url = urljoin("https://searchengines.guru", topic_link.get("href", "")) if topic_link else ""
                message = message_el.get_text(" ", strip=True) if message_el else ""
                date = time_el.get("datetime") if time_el else ""
                section = "comments"
            else:
                title_el = item.select_one(".search-result__title a")
                date_el = item.select_one(".search-result__date")
                message_el = item.select_one(".search-result__description")
                section_el = item.select_one(".search-result__section")
                title = title_el.get_text(" ", strip=True) if title_el else "No title"
                url = urljoin("https://searchengines.guru", title_el.get("href", "")) if title_el else ""
                message = message_el.get_text(" ", strip=True) if message_el else ""
                date = date_el.get_text(" ", strip=True) if date_el else ""
                section = section_el.get_text(" ", strip=True).replace(",", "") if section_el else "Unknown"
            results.append(
                {
                    "theme_name": title,
                    "url": url,
                    "date": cls._parse_date(date),
                    "message": message,
                    "section": section,
                }
            )
        return [item for item in results if item["message"]]

    @classmethod
    def _extract_topic_posts(cls, markup: str, limit: int | None = None) -> list[dict]:
        soup = BeautifulSoup(markup, "html.parser")
        title = cls._extract_topic_title(soup)

        site_posts = soup.select(".comments-list .comment, .comment-list .comment, .topic-comments .comment", limit=limit)
        if not site_posts:
            site_posts = [
                element
                for element in soup.select(".comment", limit=limit)
                if element.select_one(".comment__content")
            ]
        if site_posts:
            result = []
            for index, post in enumerate(site_posts):
                content_el = post.select_one(".comment__content")
                author_el = next(
                    (
                        post.select_one(selector)
                        for selector in (
                            ".comment__username a", ".comment__username", ".comment__author a",
                            ".comment__author", ".comment__name a", ".comment__name", ".comment__user a",
                            ".comment__user", ".username",
                        )
                        if post.select_one(selector)
                    ),
                    None,
                )
                result.append(
                    {
                        "title": title if index == 0 else "",
                        "author": author_el.get_text(" ", strip=True) if author_el else "",
                        "content": content_el.get_text("\n", strip=True) if content_el else "",
                    }
                )
            return result

        engines = (
            ("article.message--post", "article.message", ".message.message--post", "[data-author]"),
            (".postrow", "#posts .post", "li.postbitlegacy"),
            ("li.message", "#messageList > li"),
        )
        for selectors in engines:
            posts = soup.select(", ".join(selectors), limit=limit)
            if not posts:
                continue
            result = []
            for index, post in enumerate(posts):
                author_el = post.select_one(".message-name .username, .message-name a, .username, .author")
                content_el = post.select_one(
                    ".bbWrapper, .message-userContent, .message-body, .postbody, .post-message, "
                    ".messageContent article, .messageContent, .content"
                )
                result.append(
                    {
                        "title": title if index == 0 else "",
                        "author": (
                            author_el.get_text(" ", strip=True)
                            if author_el
                            else str(post.get("data-author", ""))
                        ),
                        "content": content_el.get_text("\n", strip=True) if content_el else "",
                    }
                )
            return [post for post in result if post["content"]]

        generic = []
        seen: set[str] = set()
        for index, element in enumerate(soup.select("article, [class*='post'], [class*='message']", limit=limit)):
            text = element.get_text("\n", strip=True)
            if len(text) >= 20 and text not in seen:
                generic.append({"title": title if index == 0 else "", "author": "", "content": text})
                seen.add(text)
        return generic

    @staticmethod
    def _extract_topic_title(soup: BeautifulSoup) -> str:
        for selector in ("h1.p-title-value", ".threadTitle", "h1#thread_title", ".topic-title", "h1"):
            element = soup.select_one(selector)
            if element and element.get_text(strip=True):
                return element.get_text(" ", strip=True)
        return ""

    @staticmethod
    def _next_page_url(markup: str, page_number: int, base_url: str) -> str | None:
        soup = BeautifulSoup(markup, "html.parser")
        wanted = str(page_number)
        for link in soup.select(".paginator a.paginator__page, a.pageNav-page, a[rel='next']"):
            if link.get_text(" ", strip=True) == wanted or link.get("rel") == ["next"]:
                href = link.get("href")
                if href:
                    return urljoin(base_url, href)
        return None


async def parse_user_messages(
    username: str,
    *,
    by_id: bool = False,
    max_pages: int = 1,
    timeout_ms: int = 3000,
) -> dict:
    async with _PARSER_SEMAPHORE:
        async with SearchEnginesParser() as parser:
            return await parser.parse_user(username, by_id=by_id, max_pages=max_pages, timeout_ms=timeout_ms)


async def parse_topic_by_url(url: str, *, max_messages: int = 50, max_pages: int = 20) -> dict:
    allowed_hosts = get_settings().allowed_forum_hosts
    validate_topic_url_syntax(url, allowed_hosts)
    async with _PARSER_SEMAPHORE:
        async with SearchEnginesParser(allowed_hosts) as parser:
            return await parser.parse_topic(url, max_messages=max_messages, max_pages=max_pages)
