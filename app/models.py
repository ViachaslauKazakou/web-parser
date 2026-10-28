from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="completed")
    topic_title: Mapped[str] = mapped_column(String(500), nullable=False)
    topic_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_query: Mapped[str | None] = mapped_column(String(255), nullable=True)
    messages_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    best_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    worst_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    options_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    warnings_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    items: Mapped[list["AnalysisItem"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="AnalysisItem.rank_position"
    )


class AnalysisItem(Base):
    __tablename__ = "analysis_items"
    __table_args__ = (Index("ix_analysis_items_run_rank", "run_id", "rank_position"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False)
    external_message_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    rank_position: Mapped[int] = mapped_column(Integer, nullable=False)
    base_score: Mapped[float] = mapped_column(Float, nullable=False)
    final_score: Mapped[float] = mapped_column(Float, nullable=False)
    relevance_label: Mapped[str] = mapped_column(String(24), nullable=False)
    explanation_short: Mapped[str] = mapped_column(Text, nullable=False)
    features_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    run: Mapped[AnalysisRun] = relationship(back_populates="items")
