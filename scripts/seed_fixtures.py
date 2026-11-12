from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select

from marketmind.domain.enums import EventType, ProcessingStatus, SourceType
from marketmind.infrastructure.db.models import Company, DataSource, FinancialEvent, TrackedSymbol
from marketmind.infrastructure.db.session import SessionLocal


def seed() -> None:
    with SessionLocal() as session:
        source = session.scalar(select(DataSource).where(DataSource.slug == "offline-fixture"))
        if source is None:
            source = DataSource(
                slug="offline-fixture",
                name="Offline development fixture",
                source_type=SourceType.FIXTURE.value,
                enabled=True,
            )
            session.add(source)

        for symbol, name, cik in (
            ("AAPL", "Apple Inc.", "0000320193"),
            ("MSFT", "Microsoft Corporation", "0000789019"),
        ):
            company = session.scalar(select(Company).where(Company.cik == cik))
            if company is None:
                company = Company(name=name, cik=cik)
                company.symbols.append(TrackedSymbol(symbol=symbol, exchange="NASDAQ"))
                session.add(company)

        session.flush()
        event = session.scalar(
            select(FinancialEvent).where(
                FinancialEvent.external_id == "fixture-event-quarterly-results"
            )
        )
        if event is None:
            apple = session.scalar(select(Company).where(Company.cik == "0000320193"))
            event = FinancialEvent(
                external_id="fixture-event-quarterly-results",
                company_id=apple.id if apple else None,
                event_type=EventType.EARNINGS.value,
                occurred_at=datetime(2026, 1, 30, 21, 5, tzinfo=UTC),
                published_at=datetime(2026, 1, 30, 21, 5, tzinfo=UTC),
                title="Example quarterly results",
                summary="Deterministic fixture event; no external service was accessed.",
                structured_data={"fixture": True},
                confidence=Decimal("1.0"),
                processing_status=ProcessingStatus.SUCCEEDED.value,
            )
            session.add(event)
        session.commit()


if __name__ == "__main__":
    seed()
