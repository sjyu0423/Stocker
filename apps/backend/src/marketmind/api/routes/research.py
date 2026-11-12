import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from marketmind.api.dependencies import QueryServiceDependency
from marketmind.api.schemas import FinancialEventResponse, Page, SourceRecordResponse

router = APIRouter(tags=["research"])


@router.get("/source-records", response_model=Page[SourceRecordResponse])
def list_source_records(
    service: QueryServiceDependency,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    data_source_id: uuid.UUID | None = None,
) -> Page[SourceRecordResponse]:
    items, total = service.source_records(
        page=page, page_size=page_size, data_source_id=data_source_id
    )
    return Page(
        items=[SourceRecordResponse.model_validate(item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get(
    "/source-records/{data_source_id}/{external_id}/latest",
    response_model=SourceRecordResponse,
)
def get_latest_source_revision(
    data_source_id: uuid.UUID,
    external_id: str,
    service: QueryServiceDependency,
) -> SourceRecordResponse:
    item = service.latest_source_revision(data_source_id=data_source_id, external_id=external_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Source record not found")
    return SourceRecordResponse.model_validate(item)


@router.get(
    "/source-records/{data_source_id}/{external_id}/as-of",
    response_model=SourceRecordResponse,
)
def get_source_revision_as_of(
    data_source_id: uuid.UUID,
    external_id: str,
    available_at: datetime,
    service: QueryServiceDependency,
) -> SourceRecordResponse:
    item = service.source_revision_as_of(
        data_source_id=data_source_id,
        external_id=external_id,
        available_at=available_at,
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Source record not found as of that time")
    return SourceRecordResponse.model_validate(item)


@router.get("/events", response_model=Page[FinancialEventResponse])
def list_financial_events(
    service: QueryServiceDependency,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    company_id: uuid.UUID | None = None,
) -> Page[FinancialEventResponse]:
    items, total = service.financial_events(page=page, page_size=page_size, company_id=company_id)
    return Page(
        items=[FinancialEventResponse.model_validate(item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )
