import asyncio
import socket

import pytest

from app.parser import (
    ParserInputError,
    ParserFailure,
    SafeEgressProxy,
    SearchEnginesParser,
    _assert_public_host,
    host_is_allowed,
    validate_topic_url_syntax,
)

ALLOWED = ("searchengines.guru",)


def test_host_allowlist_matches_exact_host_and_subdomains_only():
    assert host_is_allowed("searchengines.guru", ALLOWED)
    assert host_is_allowed("www.searchengines.guru", ALLOWED)
    assert not host_is_allowed("searchengines.guru.attacker.test", ALLOWED)
    assert not host_is_allowed("attackersearchengines.guru", ALLOWED)


@pytest.mark.parametrize(
    "url",
    [
        "http://searchengines.guru/ru/forum/1",
        "https://example.com/thread",
        "https://user:pass@searchengines.guru/thread",
        "https://searchengines.guru:8443/thread",
        "https://127.0.0.1/thread",
    ],
)
def test_topic_url_rejects_unsafe_scheme_host_credentials_and_port(url):
    with pytest.raises(ParserInputError):
        validate_topic_url_syntax(url, ALLOWED)


def test_topic_url_accepts_allowed_https_host():
    host = validate_topic_url_syntax("https://searchengines.guru/ru/forum/123", ALLOWED)
    assert host == "searchengines.guru"


@pytest.mark.asyncio
async def test_dns_guard_rejects_private_and_accepts_public_addresses(monkeypatch):
    private = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.4", 443))]
    monkeypatch.setattr("app.parser.socket.getaddrinfo", lambda *args, **kwargs: private)
    with pytest.raises(ParserInputError, match="локальным и внутренним"):
        await _assert_public_host("forum.test")

    public = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))]
    monkeypatch.setattr("app.parser.socket.getaddrinfo", lambda *args, **kwargs: public)
    await _assert_public_host("forum.test")


@pytest.mark.asyncio
async def test_egress_proxy_blocks_loopback_and_private_dns_and_pins_public_ip(monkeypatch):
    proxy = SafeEgressProxy(ALLOWED)
    await proxy.start()
    clients = []
    try:
        port = int(proxy.server_url.rsplit(":", 1)[1])

        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        clients.append(writer)
        writer.write(b"CONNECT 127.0.0.1:443 HTTP/1.1\r\nHost: 127.0.0.1:443\r\n\r\n")
        await writer.drain()
        assert (await reader.readline()).startswith(b"HTTP/1.1 403")

        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        clients.append(writer)
        private = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.8", 443))]
        monkeypatch.setattr("app.parser.socket.getaddrinfo", lambda *args, **kwargs: private)
        writer.write(b"CONNECT searchengines.guru:443 HTTP/1.1\r\nHost: searchengines.guru\r\n\r\n")
        await writer.drain()
        assert (await reader.readline()).startswith(b"HTTP/1.1 403")

        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        clients.append(writer)
        public = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))]
        monkeypatch.setattr("app.parser.socket.getaddrinfo", lambda *args, **kwargs: public)
        connected_hosts = []

        async def fake_open_connection(*, host, port, family):
            connected_hosts.append(host)
            raise OSError("blocked test connection")

        monkeypatch.setattr("app.parser.asyncio.open_connection", fake_open_connection)
        writer.write(b"CONNECT searchengines.guru:443 HTTP/1.1\r\nHost: searchengines.guru\r\n\r\n")
        await writer.drain()
        assert (await reader.readline()).startswith(b"HTTP/1.1 502")
        assert connected_hosts == ["8.8.8.8"]
    finally:
        for writer in clients:
            writer.close()
        await proxy.close()


@pytest.mark.asyncio
async def test_egress_proxy_stops_a_tunnel_after_the_response_byte_budget(monkeypatch):
    async def local_origin(reader, writer):
        writer.write(b"1234")
        await writer.drain()
        await asyncio.sleep(0.05)
        writer.write(b"5678")
        await writer.drain()
        await asyncio.sleep(0.05)
        writer.write(b"9")
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    origin = await asyncio.start_server(local_origin, "127.0.0.1", 0)
    origin_port = origin.sockets[0].getsockname()[1]
    async def resolve_to_local_test_origin(hostname: str, port: int) -> list[str]:
        assert hostname == "searchengines.guru"
        assert port == 443
        return ["127.0.0.1"]

    monkeypatch.setattr("app.parser._resolve_public_addresses", resolve_to_local_test_origin)
    proxy = SafeEgressProxy(ALLOWED, max_request_bytes=16, max_response_bytes=8)
    await proxy.start()
    client_writer = None
    try:
        proxy_port = int(proxy.server_url.rsplit(":", 1)[1])
        reader, client_writer = await asyncio.open_connection("127.0.0.1", proxy_port)
        real_open_connection = asyncio.open_connection

        async def connect_test_origin(*, host, port, family):
            if host == "127.0.0.1" and port == 443:
                return await real_open_connection(host=host, port=origin_port, family=family)
            return await real_open_connection(host=host, port=port, family=family)

        monkeypatch.setattr("app.parser.asyncio.open_connection", connect_test_origin)
        client_writer.write(b"CONNECT searchengines.guru:443 HTTP/1.1\r\nHost: searchengines.guru\r\n\r\n")
        await client_writer.drain()
        assert (await reader.readline()).startswith(b"HTTP/1.1 200")
        await reader.readline()
        payload = await asyncio.wait_for(reader.read(), timeout=2)
        assert payload == b"12345678"
        assert origin_port > 0
    finally:
        if client_writer:
            client_writer.close()
            await client_writer.wait_closed()
        await proxy.close()
        origin.close()
        await origin.wait_closed()


def test_search_result_parser_handles_relative_links_and_dates():
    html = """
    <div class="search-result__item">
      <div class="search-result__title"><a href="/ru/forum/123">Обсуждение</a></div>
      <div class="search-result__date">2026.10.28</div>
      <div class="search-result__description">Содержательный ответ</div>
      <div class="search-result__section">Форум, маркетинг</div>
    </div>
    """

    result = SearchEnginesParser._extract_user_page(html, comments=False)

    assert result[0]["theme_name"] == "Обсуждение"
    assert result[0]["url"] == "https://searchengines.guru/ru/forum/123"
    assert result[0]["date"].startswith("2026-10-28")
    assert result[0]["message"] == "Содержательный ответ"


def test_comment_extraction_preserves_iso_datetime():
    html = """
    <div class="comments-list"><div class="comment">
      <div class="comment__topic"><a href="/ru/forum/456">Тема</a></div>
      <div class="comment__date"><time datetime="2025-04-11T09:30:00Z"></time></div>
      <div class="comment__content">Комментарий автора</div>
    </div></div>
    """

    result = SearchEnginesParser._extract_user_page(html, comments=True)

    assert result[0]["url"] == "https://searchengines.guru/ru/forum/456"
    assert result[0]["date"].startswith("2025-04-11T09:30:00")
    assert result[0]["message"] == "Комментарий автора"


def test_topic_extraction_handles_searchengines_and_xenforo_markup():
    site_html = """
    <h1>Как настроить парсер?</h1><div class="comments-list">
      <div class="comment"><span class="comment__username">Ольга</span><div class="comment__content">Исходный вопрос про парсер.</div></div>
      <div class="comment"><span class="comment__username">Илья</span><div class="comment__content">Ответ с решением для страницы.</div></div>
    </div>
    """
    xf_html = """
    <h1 class="p-title-value">Тема XenForo</h1>
    <article class="message--post"><span class="username">Автор</span><div class="bbWrapper">Стартовое сообщение XenForo</div></article>
    <article class="message--post"><span class="username">Участник</span><div class="bbWrapper">Ответ XenForo</div></article>
    """

    site = SearchEnginesParser._extract_topic_posts(site_html)
    xenforo = SearchEnginesParser._extract_topic_posts(xf_html)

    assert site[0]["title"] == "Как настроить парсер?"
    assert site[0]["author"] == "Ольга"
    assert site[1]["content"] == "Ответ с решением для страницы."
    assert xenforo[0]["title"] == "Тема XenForo"
    assert xenforo[0]["content"] == "Стартовое сообщение XenForo"


def test_pagination_link_is_resolved_and_wrong_page_ignored():
    html = '<div class="paginator"><a class="paginator__page" href="/forum/2">2</a></div>'

    assert SearchEnginesParser._next_page_url(html, 2, "https://searchengines.guru/forum/1") == "https://searchengines.guru/forum/2"
    assert SearchEnginesParser._next_page_url(html, 3, "https://searchengines.guru/forum/1") is None


def test_user_and_topic_extraction_respect_result_limits():
    search_html = "<div class='search-result__item'><div class='search-result__description'>one</div></div>"
    search_html += "<div class='search-result__item'><div class='search-result__description'>two</div></div>"
    topic_html = "<h1>Тема</h1><div class='comments-list'>"
    topic_html += "<div class='comment'><div class='comment__content'>Первый пост темы.</div></div>"
    topic_html += "<div class='comment'><div class='comment__content'>Первый ответ.</div></div>"
    topic_html += "<div class='comment'><div class='comment__content'>Второй ответ.</div></div></div>"

    assert len(SearchEnginesParser._extract_user_page(search_html, comments=False, limit=1)) == 1
    assert len(SearchEnginesParser._extract_topic_posts(topic_html, limit=2)) == 2


@pytest.mark.asyncio
async def test_oversized_page_content_is_rejected_before_dom_parsing():
    class FakePage:
        async def content(self):
            return "<html>" + ("x" * 40) + "</html>"

    parser = SearchEnginesParser(ALLOWED)
    parser.page = FakePage()
    parser.max_page_chars = 32

    with pytest.raises(ParserFailure, match="превышает безопасный лимит"):
        await parser._bounded_page_content()
