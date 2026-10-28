import csv
import io
import math
from typing import Any

from pydantic import ValidationError

from app.config import get_settings
from app.schemas import AnalysisOptions, AnalysisRequest, MessageInput, TopicInput


class ImportErrorDetail(ValueError):
    """A user-correctable error in an uploaded analysis file."""


class ManualPayloadLoader:
    """Normalizes legacy manual JSON/CSV inputs into one validated contract."""

    def from_json(self, payload: Any) -> AnalysisRequest:
        if not isinstance(payload, dict):
            raise ImportErrorDetail("JSON root must be an object")

        topic = payload.get("topic")
        if not isinstance(topic, dict):
            topic = {
                "title": payload.get("title", ""),
                "description": payload.get("description"),
                "first_message_content": payload.get("first_message") or payload.get("first_message_content"),
                "external_id": payload.get("topic_external_id"),
            }

        if "first_message_content" not in topic:
            topic = {
                **topic,
                "first_message_content": topic.get("first_message") or payload.get("first_message"),
            }

        messages = payload.get("messages") or []
        if not isinstance(messages, list):
            raise ImportErrorDetail("The messages field must be an array")
        if len(messages) > get_settings().max_import_messages:
            raise ImportErrorDetail(f"Too many messages; maximum is {get_settings().max_import_messages}")

        normalized_messages: list[dict[str, Any]] = []
        for index, message in enumerate(messages, start=1):
            if isinstance(message, str):
                normalized_messages.append({"external_id": str(index), "content": message})
            elif isinstance(message, dict):
                normalized_messages.append(
                    {
                        **message,
                        "external_id": message.get("external_id") or message.get("message_external_id") or str(index),
                    }
                )
            else:
                raise ImportErrorDetail(f"Message {index} must be a string or object")

        try:
            return AnalysisRequest.model_validate(
                {
                    "source_type": payload.get("source_type", "manual"),
                    "topic": topic,
                    "messages": normalized_messages,
                    "options": payload.get("options") or {},
                    "source_url": payload.get("source_url") or payload.get("source_topic_ref"),
                }
            )
        except ValidationError as exc:
            raise ImportErrorDetail(self._validation_message(exc)) from exc

    def from_csv(self, text: str) -> AnalysisRequest:
        try:
            reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff"), newline=""))
            if not reader.fieldnames:
                raise ImportErrorDetail("CSV must contain a header row")
            headers = {header.strip().lstrip("\ufeff") for header in reader.fieldnames if header}
            if "content" not in headers:
                raise ImportErrorDetail("CSV must contain a 'content' column")

            rows = []
            row_limit = get_settings().max_import_messages
            for row in reader:
                if len(rows) >= row_limit:
                    raise ImportErrorDetail(f"Too many messages; maximum is {row_limit}")
                rows.append(row)
        except csv.Error as exc:
            raise ImportErrorDetail(f"Invalid CSV: {exc}") from exc

        if not rows:
            raise ImportErrorDetail("CSV must contain at least one reply row")
        if len(rows) > get_settings().max_import_messages:
            raise ImportErrorDetail(f"Too many messages; maximum is {get_settings().max_import_messages}")

        first = rows[0]
        title = (first.get("topic_title") or first.get("title") or "").strip()
        if not title:
            raise ImportErrorDetail("CSV must include a non-empty 'topic_title' column")

        messages: list[dict[str, Any]] = []
        for row_number, row in enumerate(rows, start=2):
            content = (row.get("content") or "").strip()
            if not content:
                continue
            rating: float | None = None
            if row.get("rating") not in (None, ""):
                try:
                    rating = float(row["rating"])
                except (TypeError, ValueError):
                    raise ImportErrorDetail(f"Invalid rating on CSV row {row_number}") from None
                if not math.isfinite(rating) or not -1000 <= rating <= 1000:
                    raise ImportErrorDetail(f"Rating on CSV row {row_number} must be between -1000 and 1000")
            messages.append(
                {
                    "external_id": row.get("message_external_id") or str(row_number - 1),
                    "author": (row.get("author") or "").strip() or None,
                    "content": content,
                    "rating": rating,
                    "created_at": (row.get("created_at") or "").strip() or None,
                    "metadata": {"source_row": row_number},
                }
            )

        return self.from_json(
            {
                "source_type": "manual",
                "topic": {
                    "external_id": first.get("topic_external_id") or first.get("external_topic_ref"),
                    "title": title,
                    "description": first.get("topic_description"),
                    "first_message_content": first.get("first_message_content"),
                },
                "messages": messages,
            }
        )

    @staticmethod
    def _validation_message(exc: ValidationError) -> str:
        first_error = exc.errors(include_url=False)[0]
        field = ".".join(str(part) for part in first_error.get("loc", ())) or "payload"
        return f"Invalid {field}: {first_error['msg']}"


def topic_from_parsed(result: dict[str, Any]) -> AnalysisRequest:
    """Converts a forum parser response to the shared analysis contract."""
    return AnalysisRequest(
        source_type="parsed",
        topic=TopicInput(
            title=result.get("title") or "Untitled forum topic",
            description=result.get("description"),
            first_message_content=result.get("first_message"),
            external_id=result.get("source_url"),
            metadata={"parsed_at": result.get("parsed_at"), "total_parsed": result.get("total_parsed", 0)},
        ),
        messages=[
            MessageInput(
                external_id=str(message.get("external_id") or index),
                author=message.get("author") or None,
                content=message.get("content", ""),
                created_at=message.get("created_at"),
                rating=message.get("rating"),
            )
            for index, message in enumerate(result.get("messages", []), start=1)
            if (message.get("content") or "").strip()
        ],
        options=AnalysisOptions(),
        source_url=result.get("source_url"),
    )
