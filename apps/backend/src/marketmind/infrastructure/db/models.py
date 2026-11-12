import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from marketmind.domain.enums import (
    CollectionStatus,
    EventType,
    InferenceStatus,
    ProcessingStatus,
)
from marketmind.infrastructure.db.base import Base, TimestampMixin


class Company(TimestampMixin, Base):
    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    cik: Mapped[str | None] = mapped_column(String(10), unique=True)
    lei: Mapped[str | None] = mapped_column(String(20), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    symbols: Mapped[list["TrackedSymbol"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )


class TrackedSymbol(TimestampMixin, Base):
    __tablename__ = "tracked_symbols"
    __table_args__ = (UniqueConstraint("symbol", "exchange"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    exchange: Mapped[str] = mapped_column(String(32), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    company: Mapped[Company] = relationship(back_populates="symbols")


class DataSource(TimestampMixin, Base):
    __tablename__ = "data_sources"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(2048))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    raw_records: Mapped[list["RawSourceRecord"]] = relationship(back_populates="data_source")
    source_records: Mapped[list["SourceRecord"]] = relationship(back_populates="data_source")
    collection_runs: Mapped[list["CollectionRun"]] = relationship(back_populates="data_source")
    collection_checkpoints: Mapped[list["CollectionCheckpoint"]] = relationship(
        back_populates="data_source"
    )


class SourceRecord(Base):
    """Stable provider identity; content lives in immutable revisions."""

    __tablename__ = "source_records"
    __table_args__ = (
        UniqueConstraint("data_source_id", "external_id"),
        Index("ix_source_records_first_seen", "first_seen_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    data_source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("data_sources.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    external_id: Mapped[str] = mapped_column(String(512), nullable=False)
    record_type: Mapped[str] = mapped_column(String(64), nullable=False)
    original_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    data_source: Mapped[DataSource] = relationship(back_populates="source_records")
    revisions: Mapped[list["RawSourceRecord"]] = relationship(
        back_populates="source_record",
        cascade="all, delete-orphan",
        order_by="RawSourceRecord.revision_number",
    )


class RawSourceRecord(Base):
    __tablename__ = "raw_source_records"
    __table_args__ = (
        UniqueConstraint(
            "source_record_id",
            "revision_number",
            name="uq_raw_source_records_source_record_id_revision_number",
        ),
        UniqueConstraint(
            "source_record_id",
            "content_hash",
            name="uq_raw_source_records_source_record_id_content_hash",
        ),
        Index("ix_raw_source_records_status_published", "processing_status", "published_at"),
        Index("ix_raw_source_records_availability", "source_record_id", "first_seen_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    source_record_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source_records.id", ondelete="CASCADE"), nullable=False, index=True
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    data_source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("data_sources.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    external_id: Mapped[str] = mapped_column(String(512), nullable=False)
    record_type: Mapped[str] = mapped_column(String(64), nullable=False)
    canonical_url: Mapped[str | None] = mapped_column(String(2048))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    processing_status: Mapped[str] = mapped_column(
        String(32), default=ProcessingStatus.PENDING.value, nullable=False
    )
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    data_source: Mapped[DataSource] = relationship(back_populates="raw_records")
    source_record: Mapped[SourceRecord] = relationship(back_populates="revisions")
    event_links: Mapped[list["EventSource"]] = relationship(
        back_populates="source_record", cascade="all, delete-orphan"
    )


class FinancialEvent(Base):
    __tablename__ = "financial_events"
    __table_args__ = (
        UniqueConstraint("external_id"),
        Index("ix_financial_events_type_occurred", "event_type", "occurred_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    external_id: Mapped[str] = mapped_column(String(512), nullable=False)
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), index=True
    )
    event_type: Mapped[str] = mapped_column(
        String(64), default=EventType.OTHER.value, nullable=False
    )
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    structured_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    processing_status: Mapped[str] = mapped_column(
        String(32), default=ProcessingStatus.SUCCEEDED.value, nullable=False
    )

    source_links: Mapped[list["EventSource"]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )


class EventSource(Base):
    __tablename__ = "event_sources"

    event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("financial_events.id", ondelete="CASCADE"), primary_key=True
    )
    source_record_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("raw_source_records.id", ondelete="RESTRICT"), primary_key=True
    )
    relationship_type: Mapped[str] = mapped_column(String(32), default="evidence", nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    event: Mapped[FinancialEvent] = relationship(back_populates="source_links")
    source_record: Mapped[RawSourceRecord] = relationship(back_populates="event_links")


class CollectionRun(Base):
    __tablename__ = "collection_runs"
    __table_args__ = (Index("ix_collection_runs_status_started", "status", "started_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    data_source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("data_sources.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    collector_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default=CollectionStatus.PENDING.value, nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    records_seen: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_stored: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_duplicate: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(512), unique=True)
    checkpoint_start: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    checkpoint_end: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    dry_run: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_kind: Mapped[str | None] = mapped_column(String(32))
    error_message: Mapped[str | None] = mapped_column(Text)
    run_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, default=dict, nullable=False
    )

    data_source: Mapped[DataSource] = relationship(back_populates="collection_runs")


class CollectionCheckpoint(TimestampMixin, Base):
    __tablename__ = "collection_checkpoints"
    __table_args__ = (UniqueConstraint("data_source_id", "collector_name"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    data_source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    collector_name: Mapped[str] = mapped_column(String(255), nullable=False)
    cursor: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    last_successful_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("collection_runs.id", ondelete="SET NULL")
    )
    version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lease_owner: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    data_source: Mapped[DataSource] = relationship(back_populates="collection_checkpoints")


class ModelInferenceUsage(Base):
    __tablename__ = "model_inference_usage"
    __table_args__ = (
        UniqueConstraint("provider", "external_request_id"),
        Index("ix_model_inference_usage_started", "started_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    operation: Mapped[str] = mapped_column(String(100), nullable=False)
    external_request_id: Mapped[str | None] = mapped_column(String(512))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(18, 8), default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(
        String(32), default=InferenceStatus.PENDING.value, nullable=False
    )
    usage_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, default=dict, nullable=False
    )
