import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


class DataSourceResponse(ApiModel):
    id: uuid.UUID
    slug: str
    name: str
    source_type: str
    base_url: str | None
    enabled: bool


class TrackedSymbolResponse(ApiModel):
    symbol: str
    exchange: str
    is_primary: bool
    is_active: bool


class CompanyResponse(ApiModel):
    id: uuid.UUID
    name: str
    cik: str | None
    lei: str | None
    is_active: bool
    symbols: list[TrackedSymbolResponse]


class CollectionRunResponse(ApiModel):
    id: uuid.UUID
    data_source_id: uuid.UUID
    collector_name: str
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    records_seen: int
    records_stored: int
    records_duplicate: int
    records_failed: int
    retry_count: int
    idempotency_key: str | None
    checkpoint_start: dict[str, Any] | None
    checkpoint_end: dict[str, Any] | None
    dry_run: bool
    heartbeat_at: datetime | None
    failure_kind: str | None
    error_message: str | None


class SourceRecordResponse(ApiModel):
    id: uuid.UUID
    source_record_id: uuid.UUID
    revision_number: int
    data_source_id: uuid.UUID
    external_id: str
    record_type: str
    canonical_url: str | None
    published_at: datetime | None
    first_seen_at: datetime
    ingested_at: datetime
    content_hash: str
    raw_payload: dict[str, Any]
    processing_status: str
    attempt_count: int
    last_error: str | None


class FinancialEventResponse(ApiModel):
    id: uuid.UUID
    external_id: str
    company_id: uuid.UUID | None
    event_type: str
    occurred_at: datetime | None
    published_at: datetime | None
    first_seen_at: datetime
    ingested_at: datetime
    title: str
    summary: str | None
    structured_data: dict[str, Any]
    confidence: Decimal | None
    processing_status: str


class Page[T](BaseModel):
    items: list[T]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total: int = Field(ge=0)
