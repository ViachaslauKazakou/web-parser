import pytest

from app.middleware import RequestBodyLimitMiddleware


@pytest.mark.asyncio
async def test_streamed_body_limit_rejects_before_downstream_body_parser():
    chunks = [
        {"type": "http.request", "body": b"123", "more_body": True},
        {"type": "http.request", "body": b"456", "more_body": False},
    ]
    sent = []
    downstream_received = []

    async def receive():
        return chunks.pop(0)

    async def send(message):
        sent.append(message)

    async def downstream(scope, next_receive, next_send):
        while True:
            message = await next_receive()
            downstream_received.append(message)
            if not message.get("more_body"):
                break

    middleware = RequestBodyLimitMiddleware(downstream, max_bytes=4)
    scope = {"type": "http", "method": "POST", "path": "/api/analysis", "headers": []}

    await middleware(scope, receive, send)

    assert sent[0]["status"] == 413
    assert "Тело запроса".encode("utf-8") in sent[1]["body"]
    assert len(downstream_received) == 1
