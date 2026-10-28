from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class TopicInput(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=20_000)
    first_message_content: str | None = Field(default=None, max_length=100_000)
    external_id: str | None = Field(default=None, max_length=255)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Topic title must not be blank")
        return value


class MessageInput(BaseModel):
    external_id: str | None = Field(default=None, max_length=255)
    author: str | None = Field(default=None, max_length=255)
    content: str = Field(min_length=1, max_length=50_000)
    rating: float | None = Field(default=None, ge=-1000, le=1000, allow_inf_nan=False)
    created_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("content")
    @classmethod
    def content_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Reply content must not be blank")
        return value


class AnalysisOptions(BaseModel):
    use_community_weight: bool = False
    use_llm_scoring: bool = False
    use_llm_explain: bool = False
    llm_score_weight: float = Field(default=0.35, ge=0.0, le=1.0)


class AnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    source_type: Literal["manual", "parsed"] = "manual"
    topic: TopicInput
    messages: list[MessageInput] = Field(default_factory=list, max_length=2000)
    options: AnalysisOptions = Field(default_factory=AnalysisOptions)
    source_url: str | None = None


class ParserUserRequest(BaseModel):
    username: str = Field(min_length=1, max_length=120)
    by_id: bool = False
    max_pages: int = Field(default=1, ge=1, le=100)
    timeout_ms: int = Field(default=3000, ge=500, le=10_000)

    @field_validator("username")
    @classmethod
    def username_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Username or user ID must not be blank")
        if len(value) > 120 or any(char in value for char in "\r\n\x00"):
            raise ValueError("Invalid username or user ID")
        return value


class ParserTopicRequest(BaseModel):
    topic_url: HttpUrl
    max_messages: int = Field(default=50, ge=0, le=500)
    max_pages: int = Field(default=20, ge=1, le=20)


class AnalysisItemResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    external_message_ref: str | None = None
    author: str | None = None
    content: str
    rank_position: int
    base_score: float
    final_score: float
    relevance_label: str
    explanation_short: str
    features: dict[str, Any] = Field(default_factory=dict)


class AnalysisResponse(BaseModel):
    id: int
    source_type: str
    topic_title: str
    topic_description: str | None = None
    first_message: str | None = None
    source_url: str | None = None
    messages_count: int
    created_at: datetime
    best_summary: str | None = None
    worst_summary: str | None = None
    warnings: list[str] = Field(default_factory=list)
    results: list[AnalysisItemResult] = Field(default_factory=list)


class AnalysisRunListItem(BaseModel):
    id: int
    source_type: str
    topic_title: str
    source_url: str | None = None
    messages_count: int
    created_at: datetime
    best_score: float | None = None
    high_count: int = 0


class ParserTopicResult(BaseModel):
    title: str
    description: str | None = None
    first_message: str | None = None
    messages: list[MessageInput] = Field(default_factory=list)
    source_url: str
    parsed_at: datetime
    total_parsed: int
    warning: str | None = None


class ParserUserResult(BaseModel):
    user: str
    search_url: str
    messages_count: int
    messages: list[dict[str, Any]]
    parsed_at: datetime
    mode: Literal["keyword", "comments"]
    error: str | None = None
