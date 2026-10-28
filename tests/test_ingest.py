import pytest

from app.ingest import ImportErrorDetail, ManualPayloadLoader


def test_simplified_json_keeps_first_message_and_accepts_string_replies():
    payload = ManualPayloadLoader().from_json(
        {
            "title": "Тема",
            "description": "Описание",
            "first_message": "Исходный вопрос целиком",
            "messages": ["Ответ без автора", {"author": "alex", "content": "Ответ с автором"}],
        }
    )

    assert payload.topic.first_message_content == "Исходный вопрос целиком"
    assert payload.messages[0].external_id == "1"
    assert payload.messages[0].content == "Ответ без автора"
    assert payload.messages[1].author == "alex"


def test_full_json_contract_preserves_topic_first_message_and_options():
    payload = ManualPayloadLoader().from_json(
        {
            "source_type": "parsed",
            "topic": {"title": "Тема", "first_message_content": "Вопрос", "external_id": "topic-1"},
            "messages": [{"external_id": "m-1", "content": "Ответ"}],
            "options": {"use_llm_scoring": True},
            "source_url": "https://searchengines.guru/ru/forum/1",
        }
    )

    assert payload.source_type == "parsed"
    assert payload.topic.first_message_content == "Вопрос"
    assert payload.options.use_llm_scoring is True
    assert payload.source_url.endswith("/forum/1")


def test_csv_accepts_utf8_bom_and_maps_source_columns():
    csv_text = "\ufefftopic_title,topic_description,first_message_content,message_external_id,author,content,rating\n"
    csv_text += "Тема,Контекст,Исходный вопрос,m-42,Мария,Полезный ответ,3\n"
    csv_text += "Тема,Контекст,Исходный вопрос,m-43,,Второй ответ,\n"

    payload = ManualPayloadLoader().from_csv(csv_text)

    assert payload.topic.title == "Тема"
    assert payload.topic.first_message_content == "Исходный вопрос"
    assert len(payload.messages) == 2
    assert payload.messages[0].external_id == "m-42"
    assert payload.messages[0].rating == 3
    assert payload.messages[1].rating is None


@pytest.mark.parametrize(
    "payload, expected",
    [
        ([], "JSON root must be an object"),
        ({"title": "   ", "messages": ["ответ"]}, "Invalid topic.title"),
        ({"title": "Тема", "messages": "not a list"}, "messages field must be an array"),
    ],
)
def test_json_rejects_invalid_payloads(payload, expected):
    with pytest.raises(ImportErrorDetail, match=expected):
        ManualPayloadLoader().from_json(payload)


def test_csv_requires_title_content_columns_and_finite_rating():
    loader = ManualPayloadLoader()
    with pytest.raises(ImportErrorDetail, match="content"):
        loader.from_csv("topic_title,author\nТема,alex\n")
    with pytest.raises(ImportErrorDetail, match="topic_title"):
        loader.from_csv("content\nответ\n")
    with pytest.raises(ImportErrorDetail, match="Rating"):
        loader.from_csv("topic_title,content,rating\nТема,ответ,nan\n")


def test_csv_stops_reading_as_soon_as_the_row_limit_is_exceeded(monkeypatch):
    class SmallImportLimit:
        max_import_messages = 2

    monkeypatch.setattr("app.ingest.get_settings", lambda: SmallImportLimit())
    csv_text = "topic_title,content\nТема,ответ-1\nТема,ответ-2\nТема,ответ-3\n"

    with pytest.raises(ImportErrorDetail, match="maximum is 2"):
        ManualPayloadLoader().from_csv(csv_text)
