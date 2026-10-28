from app.relevance import normalize_text, rank_messages, scoring_tokens
from app.schemas import AnalysisRequest


def test_normalizer_removes_markup_urls_and_decodes_entities():
    normalized, tokens = normalize_text("<b>Привет</b>&nbsp;мир https://example.com/path")

    assert normalized == "привет мир"
    assert tokens == ["привет", "мир"]


def test_negation_is_kept_as_a_semantic_token():
    assert "не" in scoring_tokens("Ответ не решает проблему")


def test_first_message_context_ranks_relevant_answer_before_offtopic():
    payload = AnalysisRequest.model_validate(
        {
            "source_type": "manual",
            "topic": {
                "title": "Асинхронные сессии SQLAlchemy",
                "description": "Настройка пула соединений для приложения FastAPI",
                "first_message_content": "Как правильно создавать и закрывать async-сессии SQLAlchemy?",
            },
            "messages": [
                {
                    "external_id": "answer-relevant",
                    "author": "dev",
                    "content": "Используйте async_sessionmaker и открывайте сессию внутри контекстного менеджера.",
                },
                {"external_id": "answer-offtopic", "author": "reader", "content": "Сегодня хорошая погода и яблоки очень вкусные."},
            ],
        }
    )

    results = rank_messages(payload)

    assert [item["external_message_ref"] for item in results] == ["answer-relevant", "answer-offtopic"]
    assert results[0]["rank_position"] == 1
    assert results[1]["rank_position"] == 2
    assert results[0]["final_score"] > results[1]["final_score"]
    assert results[0]["features"]["similarity_first_message"] > 0


def test_legacy_title_description_weighting_and_empty_inputs_are_stable():
    payload = AnalysisRequest.model_validate(
        {
            "topic": {"title": "FastAPI SQLAlchemy", "description": "Асинхронные сессии"},
            "messages": [
                {"content": "FastAPI SQLAlchemy используют асинхронные сессии для запросов."},
                {"content": "Да."},
            ],
        }
    )

    results = rank_messages(payload)

    assert len(results) == 2
    assert results[0]["final_score"] >= results[1]["final_score"]
    assert results[1]["features"]["short_answer_penalty"] == 0.12
    assert all(0 <= item["final_score"] <= 1 for item in results)
    assert rank_messages(payload.model_copy(update={"messages": []})) == []


def test_non_finite_rating_is_rejected():
    try:
        AnalysisRequest.model_validate(
            {"topic": {"title": "Тема"}, "messages": [{"content": "Ответ", "rating": float("nan")}]}
        )
    except ValueError:
        return
    raise AssertionError("NaN community rating must not be accepted")
