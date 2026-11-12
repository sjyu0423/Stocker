import os
import threading
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from marketmind.application.ingestion import (
    CollectionAlreadyRunningError,
    IngestionResult,
    IngestionService,
)
from marketmind.domain.entities import RawRecordInput
from marketmind.domain.enums import SourceType
from marketmind.infrastructure.db.models import (
    CollectionCheckpoint,
    DataSource,
    RawSourceRecord,
    SourceRecord,
)

POSTGRES_URL = os.getenv("TEST_POSTGRES_URL")
pytestmark = [
    pytest.mark.postgresql,
    pytest.mark.skipif(not POSTGRES_URL, reason="TEST_POSTGRES_URL is not configured"),
]


@pytest.fixture(scope="module")
def postgres_engine() -> Iterator[Engine]:
    assert POSTGRES_URL is not None
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", POSTGRES_URL)
    engine = create_engine(POSTGRES_URL, pool_pre_ping=True)

    command.downgrade(config, "base")
    command.upgrade(config, "head")
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    command.check(config)
    yield engine
    engine.dispose()


@pytest.fixture
def pg_factory(postgres_engine: Engine) -> Iterator[sessionmaker[Session]]:
    with postgres_engine.begin() as connection:
        connection.execute(
            text(
                """
                TRUNCATE TABLE
                    event_sources, financial_events, raw_source_records, source_records,
                    collection_checkpoints, collection_runs, tracked_symbols, companies,
                    model_inference_usage, data_sources
                CASCADE
                """
            )
        )
    yield sessionmaker(bind=postgres_engine, expire_on_commit=False)


def create_source(factory: sessionmaker[Session]) -> DataSource:
    with factory() as session:
        source = DataSource(
            slug="postgres-fixture",
            name="PostgreSQL fixture",
            source_type=SourceType.FIXTURE.value,
        )
        session.add(source)
        session.commit()
        session.expunge(source)
        return source


def run_concurrently(
    factory: sessionmaker[Session],
    source: DataSource,
    records: list[RawRecordInput],
) -> list[IngestionResult]:
    barrier = threading.Barrier(len(records))
    results: list[IngestionResult] = []
    errors: list[BaseException] = []
    guard = threading.Lock()

    def worker(index: int, item: RawRecordInput) -> None:
        try:
            with factory() as session:
                attached_source = session.get(DataSource, source.id)
                assert attached_source is not None
                barrier.wait(timeout=5)
                result = IngestionService(session).ingest(
                    attached_source,
                    f"concurrent-{index}",
                    [item],
                    idempotency_key=f"concurrent-{index}",
                )
                with guard:
                    results.append(result)
        except BaseException as exc:
            with guard:
                errors.append(exc)

    threads = [
        threading.Thread(target=worker, args=(index, item), daemon=True)
        for index, item in enumerate(records)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)

    assert not errors
    assert all(not thread.is_alive() for thread in threads)
    return results


def test_postgresql_constraints_indexes_and_migration_round_trip(
    postgres_engine: Engine,
) -> None:
    inspector = inspect(postgres_engine)
    assert "source_records" in inspector.get_table_names()
    source_uniques = {
        tuple(item["column_names"]) for item in inspector.get_unique_constraints("source_records")
    }
    revision_uniques = {
        tuple(item["column_names"])
        for item in inspector.get_unique_constraints("raw_source_records")
    }
    revision_indexes = {item["name"] for item in inspector.get_indexes("raw_source_records")}
    assert ("data_source_id", "external_id") in source_uniques
    assert ("source_record_id", "content_hash") in revision_uniques
    assert ("source_record_id", "revision_number") in revision_uniques
    assert "ix_raw_source_records_availability" in revision_indexes


def test_concurrent_identical_records_create_one_revision(
    pg_factory: sessionmaker[Session],
) -> None:
    source = create_source(pg_factory)
    item = RawRecordInput(
        external_id="provider:same",
        record_type="news_article",
        payload={"headline": "same"},
    )

    results = run_concurrently(pg_factory, source, [item, item])

    with pg_factory() as session:
        assert len(list(session.scalars(select(SourceRecord)))) == 1
        assert len(list(session.scalars(select(RawSourceRecord)))) == 1
    assert sorted((result.stored, result.duplicates) for result in results) == [(0, 1), (1, 0)]


def test_concurrent_changed_content_creates_ordered_revisions(
    pg_factory: sessionmaker[Session],
) -> None:
    source = create_source(pg_factory)
    with pg_factory() as session:
        attached_source = session.get(DataSource, source.id)
        assert attached_source is not None
        IngestionService(session).ingest(
            attached_source,
            "seed",
            [
                RawRecordInput(
                    external_id="provider:amended",
                    record_type="filing",
                    payload={"version": "original"},
                )
            ],
        )

    changed = [
        RawRecordInput(
            external_id="provider:amended",
            record_type="filing",
            payload={"version": version},
        )
        for version in ("correction-a", "correction-b")
    ]
    run_concurrently(pg_factory, source, changed)

    with pg_factory() as session:
        revisions = list(
            session.scalars(select(RawSourceRecord).order_by(RawSourceRecord.revision_number))
        )
    assert [item.revision_number for item in revisions] == [1, 2, 3]
    assert {item.raw_payload["version"] for item in revisions[1:]} == {
        "correction-a",
        "correction-b",
    }


def test_database_lock_rejects_overlapping_collector(
    pg_factory: sessionmaker[Session],
) -> None:
    source = create_source(pg_factory)
    with pg_factory() as owner:
        owner.add(
            CollectionCheckpoint(
                data_source_id=source.id,
                collector_name="locked",
                lease_owner=source.id,
                lease_expires_at=datetime.now(UTC) + timedelta(minutes=5),
            )
        )
        owner.commit()
    with pg_factory() as contender:
        attached_source = contender.get(DataSource, source.id)
        assert attached_source is not None
        with pytest.raises(CollectionAlreadyRunningError):
            IngestionService(contender).ingest(attached_source, "locked", [])
