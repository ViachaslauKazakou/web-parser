import csv
import asyncio
import io
import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis_service import analyze_and_store, get_run, list_runs, run_to_dict
from app.config import get_settings
from app.database import get_session
from app.ingest import ImportErrorDetail, ManualPayloadLoader
from app.models import AnalysisItem, AnalysisRun
from app.parser import ParserFailure, ParserInputError, parse_topic_by_url, parse_user_messages
from app.schemas import AnalysisRequest, ParserTopicRequest, ParserUserRequest

router = APIRouter(prefix="/api")


def _spreadsheet_safe(value):
    if not isinstance(value, str):
        return value
    first = value.lstrip(" \t\r\n\ufeff")
    return f"\t{first}" if first.startswith(("=", "+", "-", "@", "＝", "＋", "－", "＠")) else value


def _csv_record(values: list) -> str:
    output = io.StringIO(newline="")
    csv.writer(output, quoting=csv.QUOTE_ALL, lineterminator="\r\n").writerow(
        [_spreadsheet_safe(value) for value in values]
    )
    return output.getvalue()


@router.get("/health")
async def health(session: AsyncSession = Depends(get_session)) -> dict[str, str]:
    await session.execute(text("SELECT 1"))
    return {"status": "ok", "database": "ok"}


@router.post("/parser/user")
async def parse_user(payload: ParserUserRequest) -> dict:
    settings = get_settings()
    try:
        async with asyncio.timeout(settings.parser_total_timeout_seconds):
            result = await parse_user_messages(
                payload.username,
                by_id=payload.by_id,
                max_pages=max(1, min(payload.max_pages, settings.max_parser_pages, 100)),
                timeout_ms=payload.timeout_ms,
            )
    except ParserInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="Поиск превысил общий лимит времени.") from exc
    except ParserFailure as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Не удалось выполнить поиск на форуме.") from exc

    if not result.get("messages"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Сообщения не найдены.")
    return result


@router.post("/parser/topic")
async def parse_topic(payload: ParserTopicRequest) -> dict:
    settings = get_settings()
    try:
        async with asyncio.timeout(settings.parser_total_timeout_seconds):
            result = await parse_topic_by_url(
                str(payload.topic_url),
                max_messages=payload.max_messages,
                max_pages=max(1, min(payload.max_pages, settings.max_parser_pages, 20)),
            )
    except ParserInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="Разбор темы превысил общий лимит времени.") from exc
    except ParserFailure as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Не удалось разобрать тему форума.") from exc
    return result


@router.post("/analysis", status_code=status.HTTP_201_CREATED)
async def analyze(payload: AnalysisRequest, session: AsyncSession = Depends(get_session)) -> dict:
    if len(payload.messages) > get_settings().max_import_messages:
        raise HTTPException(status_code=413, detail="Превышен лимит ответов для одного анализа.")
    try:
        run = await analyze_and_store(session, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return run_to_dict(run)


@router.post("/analysis/import", status_code=status.HTTP_201_CREATED)
async def import_and_analyze(
    file: UploadFile = File(...),
    use_community_weight: bool = Form(default=False),
    use_llm_scoring: bool = Form(default=False),
    use_llm_explain: bool = Form(default=False),
    session: AsyncSession = Depends(get_session),
) -> dict:
    settings = get_settings()
    filename = (file.filename or "").lower()
    if not filename.endswith((".json", ".csv")):
        raise HTTPException(status_code=415, detail="Поддерживаются только файлы JSON и CSV.")
    raw = await file.read(settings.max_upload_bytes + 1)
    if len(raw) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="Файл превышает установленный лимит 5 МБ.")
    if not raw:
        raise HTTPException(status_code=422, detail="Файл пуст.")

    loader = ManualPayloadLoader()
    try:
        if filename.endswith(".json"):
            payload = loader.from_json(json.loads(raw.decode("utf-8-sig")))
        else:
            payload = loader.from_csv(raw.decode("utf-8-sig"))
        payload.options.use_community_weight = use_community_weight
        payload.options.use_llm_scoring = use_llm_scoring
        payload.options.use_llm_explain = use_llm_explain
        if len(payload.messages) > settings.max_import_messages:
            raise ImportErrorDetail(f"Слишком много ответов; максимум {settings.max_import_messages}.")
        run = await analyze_and_store(session, payload)
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail="Файл должен быть в кодировке UTF-8.") from exc
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail=f"Некорректный JSON: {exc.msg}.") from exc
    except ImportErrorDetail as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return run_to_dict(run)


@router.get("/runs")
async def runs(
    limit: int = Query(default=50, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    stored = await list_runs(session, limit)
    return stored


@router.get("/runs/{run_id}")
async def run_detail(run_id: int, session: AsyncSession = Depends(get_session)) -> dict:
    run = await get_run(session, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Анализ не найден.")
    return run_to_dict(run)


@router.get("/runs/{run_id}/export.json")
async def export_json(run_id: int, session: AsyncSession = Depends(get_session)) -> JSONResponse:
    run = await get_run(session, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Анализ не найден.")
    data = run_to_dict(run)
    data["created_at"] = data["created_at"].isoformat()
    return JSONResponse(
        content=data,
        headers={"Content-Disposition": f'attachment; filename="forumscope-analysis-{run_id}.json"'},
    )


@router.get("/runs/{run_id}/export.csv")
async def export_csv(run_id: int, session: AsyncSession = Depends(get_session)) -> StreamingResponse:
    run = await session.get(AnalysisRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Анализ не найден.")

    result = await session.stream_scalars(
        select(AnalysisItem)
        .where(AnalysisItem.run_id == run_id)
        .order_by(AnalysisItem.rank_position.asc())
    )

    async def rows():
        try:
            yield "\ufeff"
            yield _csv_record(
                [
                    "topic_title", "topic_description", "message_external_id", "author", "content", "rank_position",
                    "base_score", "final_score", "relevance_label", "explanation",
                ]
            )
            async for item in result:
                yield _csv_record(
                    [
                        run.topic_title,
                        run.topic_description or "",
                        item.external_message_ref or "",
                        item.author or "",
                        item.content,
                        item.rank_position,
                        item.base_score,
                        item.final_score,
                        item.relevance_label,
                        item.explanation_short,
                    ]
                )
        finally:
            await result.close()

    filename = f"forumscope-analysis-{run_id}.csv"
    return StreamingResponse(
        rows(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/analysis/from-parsed-topic", status_code=status.HTTP_201_CREATED)
async def analyze_parsed_topic(
    payload: ParserTopicRequest,
    use_llm_scoring: bool = Query(default=False),
    use_llm_explain: bool = Query(default=False),
    session: AsyncSession = Depends(get_session),
) -> dict:
    settings = get_settings()
    try:
        async with asyncio.timeout(settings.parser_total_timeout_seconds):
            parsed = await parse_topic_by_url(
                str(payload.topic_url),
                max_messages=payload.max_messages,
                max_pages=max(1, min(payload.max_pages, settings.max_parser_pages, 20)),
            )
    except ParserInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="Разбор темы превысил общий лимит времени.") from exc
    except ParserFailure as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Не удалось разобрать тему форума.") from exc

    from app.ingest import topic_from_parsed

    analysis_payload = topic_from_parsed(parsed)
    analysis_payload.options.use_llm_scoring = use_llm_scoring
    analysis_payload.options.use_llm_explain = use_llm_explain
    try:
        run = await analyze_and_store(session, analysis_payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return run_to_dict(run)
