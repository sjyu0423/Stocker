import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from marketmind.infrastructure.db.models import (
    CollectionRun,
    Company,
    DataSource,
    FinancialEvent,
    RawSourceRecord,
    SourceRecord,
)


class QueryService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def data_sources(self) -> list[DataSource]:
        return list(self.session.scalars(select(DataSource).order_by(DataSource.slug)))

    def companies(self) -> list[Company]:
        query = select(Company).options(selectinload(Company.symbols)).order_by(Company.name)
        return list(self.session.scalars(query))

    def collection_runs(self, *, limit: int = 50) -> list[CollectionRun]:
        query = select(CollectionRun).order_by(CollectionRun.started_at.desc()).limit(limit)
        return list(self.session.scalars(query))

    def collection_run(self, run_id: uuid.UUID) -> CollectionRun | None:
        return self.session.get(CollectionRun, run_id)

    def source_records(
        self, *, page: int, page_size: int, data_source_id: uuid.UUID | None = None
    ) -> tuple[list[RawSourceRecord], int]:
        filters = (
            [RawSourceRecord.data_source_id == data_source_id] if data_source_id is not None else []
        )
        query = select(RawSourceRecord).where(*filters)
        count_query = select(func.count()).select_from(RawSourceRecord).where(*filters)
        items = self.session.scalars(
            query.order_by(RawSourceRecord.ingested_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(items), int(self.session.scalar(count_query) or 0)

    def latest_source_revision(
        self, *, data_source_id: uuid.UUID, external_id: str
    ) -> RawSourceRecord | None:
        return self.session.scalar(
            select(RawSourceRecord)
            .join(SourceRecord, RawSourceRecord.source_record_id == SourceRecord.id)
            .where(
                SourceRecord.data_source_id == data_source_id,
                SourceRecord.external_id == external_id,
            )
            .order_by(RawSourceRecord.revision_number.desc())
            .limit(1)
        )

    def source_revision_as_of(
        self,
        *,
        data_source_id: uuid.UUID,
        external_id: str,
        available_at: datetime,
    ) -> RawSourceRecord | None:
        return self.session.scalar(
            select(RawSourceRecord)
            .join(SourceRecord, RawSourceRecord.source_record_id == SourceRecord.id)
            .where(
                SourceRecord.data_source_id == data_source_id,
                SourceRecord.external_id == external_id,
                RawSourceRecord.first_seen_at <= available_at,
            )
            .order_by(
                RawSourceRecord.first_seen_at.desc(),
                RawSourceRecord.revision_number.desc(),
            )
            .limit(1)
        )

    def financial_events(
        self, *, page: int, page_size: int, company_id: uuid.UUID | None = None
    ) -> tuple[list[FinancialEvent], int]:
        filters = [FinancialEvent.company_id == company_id] if company_id is not None else []
        query = select(FinancialEvent).where(*filters)
        count_query = select(func.count()).select_from(FinancialEvent).where(*filters)
        items = self.session.scalars(
            query.order_by(FinancialEvent.ingested_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(items), int(self.session.scalar(count_query) or 0)
