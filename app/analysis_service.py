from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.llm import enrich_with_llm
from app.models import AnalysisItem, AnalysisRun
from app.relevance import rank_messages
from app.schemas import AnalysisRequest


def _default_summaries(results: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    if not results:
        return None, None
    return results[0]["explanation_short"], results[-1]["explanation_short"]


async def analyze_and_store(session: AsyncSession, payload: AnalysisRequest) -> AnalysisRun:
    if not payload.messages:
        raise ValueError("Добавьте хотя бы один ответ для анализа.")

    results = rank_messages(payload)
    best_summary, worst_summary = _default_summaries(results)
    options = payload.options
    llm_topic = {
        **payload.topic.model_dump(),
        "llm_score_weight": options.llm_score_weight,
    }
    results, llm_best, llm_worst, warnings = await enrich_with_llm(
        llm_topic,
        results,
        score=options.use_llm_scoring,
        explain=options.use_llm_explain,
    )
    best_summary = llm_best or best_summary
    worst_summary = llm_worst or worst_summary

    finished_at = datetime.now(timezone.utc)
    run = AnalysisRun(
        source_type=payload.source_type,
        status="completed",
        topic_title=payload.topic.title,
        topic_description=payload.topic.description,
        first_message=payload.topic.first_message_content,
        source_url=payload.source_url or payload.topic.external_id,
        messages_count=len(payload.messages),
        best_summary=best_summary,
        worst_summary=worst_summary,
        options_json=options.model_dump(),
        warnings_json=warnings,
        created_at=finished_at,
        finished_at=finished_at,
    )
    run.items = [
        AnalysisItem(
            external_message_ref=result["external_message_ref"],
            author=result["author"],
            content=result["content"],
            rank_position=result["rank_position"],
            base_score=result["base_score"],
            final_score=result["final_score"],
            relevance_label=result["relevance_label"],
            explanation_short=result["explanation_short"],
            features_json=result["features"],
        )
        for result in results
    ]
    session.add(run)
    await session.commit()
    await session.refresh(run)
    await session.refresh(run, attribute_names=["items"])
    return run


async def get_run(session: AsyncSession, run_id: int) -> AnalysisRun | None:
    result = await session.execute(
        select(AnalysisRun).where(AnalysisRun.id == run_id).options(selectinload(AnalysisRun.items))
    )
    return result.scalar_one_or_none()


async def list_runs(session: AsyncSession, limit: int = 50) -> list[dict[str, Any]]:
    best_score = (
        select(AnalysisItem.final_score)
        .where(AnalysisItem.run_id == AnalysisRun.id)
        .order_by(AnalysisItem.rank_position.asc())
        .limit(1)
        .scalar_subquery()
    )
    high_count = (
        select(func.count(AnalysisItem.id))
        .where(AnalysisItem.run_id == AnalysisRun.id, AnalysisItem.relevance_label == "high")
        .scalar_subquery()
    )
    result = await session.execute(
        select(
            AnalysisRun.id,
            AnalysisRun.source_type,
            AnalysisRun.topic_title,
            AnalysisRun.source_url,
            AnalysisRun.messages_count,
            AnalysisRun.created_at,
            best_score.label("best_score"),
            high_count.label("high_count"),
        )
        .order_by(AnalysisRun.created_at.desc(), AnalysisRun.id.desc())
        .limit(limit)
    )
    return [dict(row._mapping) for row in result.all()]


def run_to_dict(run: AnalysisRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "source_type": run.source_type,
        "topic_title": run.topic_title,
        "topic_description": run.topic_description,
        "first_message": run.first_message,
        "source_url": run.source_url,
        "messages_count": run.messages_count,
        "created_at": run.created_at,
        "best_summary": run.best_summary,
        "worst_summary": run.worst_summary,
        "warnings": run.warnings_json or [],
        "results": [
            {
                "external_message_ref": item.external_message_ref,
                "author": item.author,
                "content": item.content,
                "rank_position": item.rank_position,
                "base_score": item.base_score,
                "final_score": item.final_score,
                "relevance_label": item.relevance_label,
                "explanation_short": item.explanation_short,
                "features": item.features_json or {},
            }
            for item in run.items
        ],
    }
