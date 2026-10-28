import json
import asyncio

from fastapi.testclient import TestClient
from app.config import get_settings


def test_web_interface_is_directly_accessible_without_auth(client: TestClient):
    response = client.get("/")

    assert response.status_code == 200
    assert "Новый анализ" in response.text
    assert "Войти" not in response.text
    assert client.get("/static/styles.css").status_code == 200
    assert client.get("/static/app.js").status_code == 200


def test_health_and_saved_analysis_history(client: TestClient):
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok", "database": "ok"}

    created = client.post(
        "/api/analysis",
        json={
            "topic": {"title": "Планирование сессий FastAPI", "description": "SQLAlchemy async"},
            "messages": [
                {"external_id": "m-1", "author": "Мария", "content": "Используйте async_sessionmaker и контекстный менеджер."},
                {
                    "external_id": "m-2",
                    "author": "=1+1",
                    "content": "=HYPERLINK(\"https://example.invalid/\",\"open\")",
                },
            ],
        },
    )
    assert created.status_code == 201
    result = created.json()
    assert result["messages_count"] == 2
    assert result["results"][0]["rank_position"] == 1
    assert result["results"][0]["external_message_ref"] == "m-1"

    history = client.get("/api/runs")
    assert history.status_code == 200
    assert history.json()[0]["topic_title"] == "Планирование сессий FastAPI"
    assert history.json()[0]["messages_count"] == 2

    detail = client.get(f"/api/runs/{result['id']}")
    assert detail.status_code == 200
    assert detail.json()["results"][0]["content"].startswith("Используйте")

    exported = client.get(f"/api/runs/{result['id']}/export.json")
    assert exported.status_code == 200
    assert exported.headers["content-disposition"].endswith(f'forumscope-analysis-{result["id"]}.json"')
    assert json.loads(exported.text)["topic_title"] == "Планирование сессий FastAPI"

    csv_export = client.get(f"/api/runs/{result['id']}/export.csv")
    assert csv_export.status_code == 200
    assert "message_external_id" in csv_export.text
    assert "m-1" in csv_export.text
    assert '"\t=1+1"' in csv_export.text
    assert '"\t=HYPERLINK' in csv_export.text


def test_json_and_csv_import_run_through_same_pipeline(client: TestClient):
    json_response = client.post(
        "/api/analysis/import",
        files={
            "file": (
                "thread.json",
                json.dumps(
                    {
                        "title": "Новая тема",
                        "first_message": "Как настроить playwright?",
                        "messages": [{"author": "Лена", "content": "Используйте async_playwright и закройте browser."}],
                    }
                ),
                "application/json",
            )
        },
    )
    assert json_response.status_code == 201
    assert json_response.json()["first_message"] == "Как настроить playwright?"

    csv_response = client.post(
        "/api/analysis/import",
        files={"file": ("thread.csv", "topic_title,content,author\nCSV тема,Первый ответ,Олег\n", "text/csv")},
    )
    assert csv_response.status_code == 201
    assert csv_response.json()["topic_title"] == "CSV тема"


def test_invalid_inputs_return_recoverable_errors_and_unknown_runs_404(client: TestClient):
    no_messages = client.post("/api/analysis", json={"topic": {"title": "Тема"}, "messages": []})
    assert no_messages.status_code == 422
    assert "Добавьте хотя бы один ответ" in no_messages.json()["detail"]

    bad_file = client.post("/api/analysis/import", files={"file": ("data.txt", "x", "text/plain")})
    assert bad_file.status_code == 415
    assert client.get("/api/runs/99999").status_code == 404

    oversized = client.post(
        "/api/analysis",
        content=b"x" * 4097,
        headers={"content-type": "application/json"},
    )
    assert oversized.status_code == 413
    assert "Тело запроса" in oversized.json()["detail"]


def test_parser_host_allowlist_is_enforced_before_network_access(client: TestClient):
    response = client.post(
        "/api/parser/topic",
        json={"topic_url": "https://example.com/thread", "max_messages": 10},
    )

    assert response.status_code == 422
    assert "PARSER_ALLOWED_HOSTS" in response.json()["detail"]


def test_user_parser_caps_requested_page_count(client: TestClient, monkeypatch):
    captured = {}

    async def fake_parse_user(username: str, *, by_id: bool, max_pages: int, timeout_ms: int):
        captured["max_pages"] = max_pages
        return {"user": username, "messages": [{"message": "ok"}], "messages_count": 1}

    monkeypatch.setattr("app.api.parse_user_messages", fake_parse_user)
    response = client.post("/api/parser/user", json={"username": "member", "max_pages": 100})

    assert response.status_code == 200
    assert captured["max_pages"] == get_settings().max_parser_pages


def test_user_parser_obeys_global_deadline(client: TestClient, monkeypatch):
    monkeypatch.setattr(get_settings(), "parser_total_timeout_seconds", 0.01)

    async def slow_parse_user(username: str, *, by_id: bool, max_pages: int, timeout_ms: int):
        await asyncio.sleep(0.05)
        return {"user": username, "messages": [{"message": "late"}], "messages_count": 1}

    monkeypatch.setattr("app.api.parse_user_messages", slow_parse_user)
    response = client.post("/api/parser/user", json={"username": "member", "max_pages": 1})

    assert response.status_code == 504
    assert "общий лимит времени" in response.json()["detail"]


def test_parse_and_analyze_endpoint_persists_parser_output(client: TestClient, monkeypatch):
    async def fake_parse_topic(url: str, *, max_messages: int = 50, max_pages: int = 20):
        return {
            "title": "Разобранная тема",
            "description": "Описание темы",
            "first_message": "Исходный вопрос",
            "messages": [{"external_id": "reply-1", "author": "Вера", "content": "Содержательный ответ на исходный вопрос."}],
            "source_url": url,
            "parsed_at": "2026-10-28T12:00:00+00:00",
            "total_parsed": 1,
        }

    monkeypatch.setattr("app.api.parse_topic_by_url", fake_parse_topic)
    response = client.post(
        "/api/analysis/from-parsed-topic",
        json={"topic_url": "https://searchengines.guru/ru/forum/123", "max_messages": 20},
    )

    assert response.status_code == 201
    assert response.json()["source_type"] == "parsed"
    assert response.json()["topic_title"] == "Разобранная тема"
    assert response.json()["results"][0]["external_message_ref"] == "reply-1"
