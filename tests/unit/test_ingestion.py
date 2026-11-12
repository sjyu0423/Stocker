from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from marketmind.application.ingestion import IngestionService
from marketmind.application.queries import QueryService
from marketmind.domain.entities import RawRecordInput
from marketmind.domain.enums import CollectionStatus, ProcessingStatus, SourceType
from marketmind.infrastructure.db.models import (
    CollectionCheckpoint,
    CollectionRun,
    DataSource,
    RawSourceRecord,
    SourceRecord,
)


class MutableClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value


def record(headline: str = "Stable evidence") -> RawRecordInput:
    return RawRecordInput(
        external_id="provider:123",
        record_type="news_article",
        payload={"headline": headline},
        published_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def source(session: Session) -> DataSource:
    item = DataSource(slug="fixture", name="Fixture", source_type=SourceType.FIXTURE.value)
    session.add(item)
    session.commit()
    return item


def test_repeated_identical_ingestion_is_a_no_op(session: Session) -> None:
    data_source = source(session)
    service = IngestionService(session)

    first = service.ingest(data_source, "fixture", [record()])
    second = service.ingest(data_source, "fixture", [record()])

    assert first.stored == 1
    assert second.duplicates == 1
    assert session.scalar(select(func.count()).select_from(SourceRecord)) == 1
    assert session.scalar(select(func.count()).select_from(RawSourceRecord)) == 1


def test_changed_content_creates_immutable_revision_and_as_of_history(
    session: Session,
) -> None:
    data_source = source(session)
    first_seen = datetime(2026, 2, 1, 12, tzinfo=UTC)
    second_seen = datetime(2026, 2, 2, 12, tzinfo=UTC)
    clock = MutableClock(first_seen)
    service = IngestionService(session, clock=clock)

    service.ingest(data_source, "fixture", [record("Original")])
    clock.value = second_seen
    service.ingest(data_source, "fixture", [record("Corrected")])

    identity = session.scalar(select(SourceRecord))
    revisions = list(
        session.scalars(select(RawSourceRecord).order_by(RawSourceRecord.revision_number))
    )
    queries = QueryService(session)

    assert identity is not None
    assert identity.first_seen_at.replace(tzinfo=UTC) == first_seen
    assert identity.original_published_at is not None
    assert identity.original_published_at.replace(tzinfo=UTC) == datetime(2026, 1, 1, tzinfo=UTC)
    assert [item.raw_payload["headline"] for item in revisions] == ["Original", "Corrected"]
    assert (
        queries.latest_source_revision(data_source_id=data_source.id, external_id="provider:123")
        is revisions[1]
    )
    historical = queries.source_revision_as_of(
        data_source_id=data_source.id,
        external_id="provider:123",
        available_at=first_seen + timedelta(hours=1),
    )
    assert historical is revisions[0]


def test_idempotency_key_and_checkpoint_make_task_replay_safe(session: Session) -> None:
    data_source = source(session)
    service = IngestionService(session)

    first = service.ingest(
        data_source,
        "fixture",
        [record()],
        idempotency_key="fixture-page-1",
        next_cursor={"page": 2},
    )
    replay = service.ingest(
        data_source,
        "fixture",
        [record("would otherwise be a revision")],
        idempotency_key="fixture-page-1",
        next_cursor={"page": 999},
    )
    checkpoint = session.scalar(select(CollectionCheckpoint))

    assert replay == first
    assert checkpoint is not None
    assert checkpoint.cursor == {"page": 2}
    assert checkpoint.version == 1
    assert session.scalar(select(func.count()).select_from(CollectionRun)) == 1
    assert session.scalar(select(func.count()).select_from(RawSourceRecord)) == 1


def test_transaction_rollback_does_not_advance_checkpoint(session: Session) -> None:
    data_source = source(session)

    class FailingService(IngestionService):
        calls = 0

        def _store_revision(  # type: ignore[override]
            self, data_source_id: object, item: RawRecordInput, observed_at: datetime
        ) -> bool:
            self.calls += 1
            if self.calls == 2:
                raise RuntimeError("simulated interruption")
            return super()._store_revision(data_source_id, item, observed_at)  # type: ignore[arg-type]

    service = FailingService(session)
    with pytest.raises(RuntimeError, match="simulated interruption"):
        service.ingest(
            data_source,
            "fixture",
            [
                record("first"),
                RawRecordInput(
                    external_id="provider:456",
                    record_type="news_article",
                    payload={"headline": "second"},
                ),
            ],
            idempotency_key="interrupted-page",
            next_cursor={"page": 2},
        )

    run = session.scalar(select(CollectionRun))
    checkpoint = session.scalar(select(CollectionCheckpoint))
    assert run is not None and run.status == CollectionStatus.INTERRUPTED.value
    assert checkpoint is not None and checkpoint.cursor is None
    assert session.scalar(select(func.count()).select_from(RawSourceRecord)) == 0


def test_stale_run_recovery_preserves_checkpoint(session: Session) -> None:
    data_source = source(session)
    now = datetime(2026, 2, 1, 12, tzinfo=UTC)
    checkpoint = CollectionCheckpoint(
        data_source_id=data_source.id,
        collector_name="fixture",
        cursor={"page": 4},
        lease_owner=data_source.id,
        lease_expires_at=now - timedelta(minutes=1),
    )
    run = CollectionRun(
        data_source_id=data_source.id,
        collector_name="fixture",
        status=CollectionStatus.RUNNING.value,
        started_at=now - timedelta(hours=2),
        heartbeat_at=now - timedelta(hours=2),
    )
    session.add_all([checkpoint, run])
    session.commit()

    recovered = IngestionService(session, clock=lambda: now).recover_interrupted_runs(
        stale_after=timedelta(minutes=10)
    )

    assert recovered == 1
    assert run.status == CollectionStatus.INTERRUPTED.value
    assert checkpoint.cursor == {"page": 4}
    assert checkpoint.lease_owner is None


def test_dry_run_validates_without_writes(session: Session) -> None:
    data_source = source(session)
    result = IngestionService(session).ingest(data_source, "fixture", [record()], dry_run=True)

    assert result.dry_run is True
    assert result.stored == 1
    assert result.collection_run_id is None
    assert session.scalar(select(func.count()).select_from(SourceRecord)) == 0
    assert session.scalar(select(func.count()).select_from(CollectionRun)) == 0


def test_retry_metadata_transitions_to_permanent_failure(session: Session) -> None:
    data_source = source(session)
    service = IngestionService(session, max_attempts=2)
    service.ingest(data_source, "fixture", [record()])
    stored = session.scalar(select(RawSourceRecord))
    assert stored is not None

    service.mark_processing_failed(stored, ValueError("invalid fixture"))
    assert stored.processing_status == ProcessingStatus.RETRY_SCHEDULED.value
    assert stored.next_retry_at is not None

    service.mark_processing_failed(stored, ValueError("still invalid"))
    assert stored.processing_status == ProcessingStatus.PERMANENT_FAILURE.value
    assert stored.next_retry_at is None
