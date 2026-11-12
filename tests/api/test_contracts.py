from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from marketmind.application.ingestion import IngestionService
from marketmind.domain.entities import RawRecordInput
from marketmind.domain.enums import CollectionStatus, EventType, SourceType
from marketmind.infrastructure.db.models import (
    CollectionRun,
    Company,
    DataSource,
    FinancialEvent,
    TrackedSymbol,
)


def seed(session: Session) -> None:
    company = Company(name="Example Corp", cik="0000000001")
    company.symbols.append(TrackedSymbol(symbol="EXM", exchange="NASDAQ"))
    source = DataSource(slug="fixture", name="Fixture", source_type=SourceType.FIXTURE.value)
    session.add_all([company, source])
    session.flush()
    session.add_all(
        [
            CollectionRun(
                data_source_id=source.id,
                collector_name="fixture",
                status=CollectionStatus.SUCCEEDED.value,
                started_at=datetime.now(UTC),
            ),
            FinancialEvent(
                external_id="event:1",
                company_id=company.id,
                event_type=EventType.EARNINGS.value,
                title="Quarterly result",
                structured_data={"revenue": 100},
            ),
        ]
    )
    session.commit()


def test_health_contract(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "marketmind-api",
        "version": "0.1.0",
    }


def test_catalog_and_research_contracts(client: TestClient, session: Session) -> None:
    seed(session)

    companies = client.get("/api/v1/companies")
    sources = client.get("/api/v1/data-sources")
    runs = client.get("/api/v1/collection-runs")
    events = client.get("/api/v1/events?page=1&page_size=10")
    records = client.get("/api/v1/source-records?page=1&page_size=10")

    assert companies.status_code == sources.status_code == runs.status_code == 200
    assert companies.json()[0]["symbols"][0]["symbol"] == "EXM"
    assert sources.json()[0]["slug"] == "fixture"
    assert runs.json()[0]["status"] == "succeeded"
    assert events.json()["items"][0]["external_id"] == "event:1"
    assert records.json() == {"items": [], "page": 1, "page_size": 10, "total": 0}


def test_collection_run_not_found(client: TestClient) -> None:
    response = client.get("/api/v1/collection-runs/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


def test_latest_and_as_of_source_revision_contracts(client: TestClient, session: Session) -> None:
    source = DataSource(
        slug="revision-fixture",
        name="Revision fixture",
        source_type=SourceType.FIXTURE.value,
    )
    session.add(source)
    session.commit()
    first_seen = datetime(2026, 2, 1, 12, tzinfo=UTC)
    service = IngestionService(session, clock=lambda: first_seen)
    service.ingest(
        source,
        "fixture",
        [
            RawRecordInput(
                external_id="provider:contract",
                record_type="news",
                payload={"version": 1},
            )
        ],
    )
    second_seen = datetime(2026, 2, 2, 12, tzinfo=UTC)
    IngestionService(session, clock=lambda: second_seen).ingest(
        source,
        "fixture",
        [
            RawRecordInput(
                external_id="provider:contract",
                record_type="news",
                payload={"version": 2},
            )
        ],
    )

    base = f"/api/v1/source-records/{source.id}/provider:contract"
    latest = client.get(f"{base}/latest")
    historical = client.get(f"{base}/as-of", params={"available_at": "2026-02-01T13:00:00Z"})

    assert latest.status_code == historical.status_code == 200
    assert latest.json()["revision_number"] == 2
    assert latest.json()["raw_payload"] == {"version": 2}
    assert historical.json()["revision_number"] == 1
