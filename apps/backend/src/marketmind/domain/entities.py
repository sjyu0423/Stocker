from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RawRecordInput(BaseModel):
    """Provider-neutral evidence entering the ingestion boundary."""

    model_config = ConfigDict(frozen=True)

    external_id: str = Field(min_length=1, max_length=512)
    record_type: str = Field(min_length=1, max_length=64)
    payload: dict[str, Any]
    published_at: datetime | None = None
    canonical_url: str | None = Field(default=None, max_length=2048)

    @field_validator("external_id", "record_type")
    @classmethod
    def strip_identifiers(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped


class InferenceRequest(BaseModel):
    operation: str
    input_data: dict[str, Any]
    schema_name: str


class InferenceResult(BaseModel):
    output_data: dict[str, Any]
    provider: str
    model_name: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0
