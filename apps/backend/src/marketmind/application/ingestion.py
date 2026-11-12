import hashlib
import json
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.exc import DBAPIError, IntegrityError, OperationalError
from sqlalchemy.orm import Session

from marketmind.domain.entities import RawRecordInput
from marketmind.domain.enums import CollectionStatus, FailureKind, ProcessingStatus
from marketmind.infrastructure.db.models import (
    CollectionCheckpoint,
    CollectionRun,
    DataSource,
    RawSourceRecord,
    SourceRecord,
)

RETRYABLE_SQLSTATES = {"40001", "40P01", "23505"}


class CollectionAlreadyRunningError(RuntimeError):
    """Another worker owns the database coordination lock."""


@dataclass(frozen=True)
class IngestionResult:
    collection_run_id: uuid.UUID | None
    seen: int
    stored: int
    duplicates: int
    failed: int
    dry_run: bool = False
    checkpoint: dict[str, Any] | None = None


def canonical_payload_hash(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


class IngestionService:
    """Transactional, revision-aware ingestion with database-backed coordination."""

    def __init__(
        self,
        session: Session,
        *,
        max_attempts: int = 3,
        max_transaction_retries: int = 3,
        lease_ttl: timedelta = timedelta(minutes=15),
        clock: Callable[[], datetime] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.session = session
        self.max_attempts = max_attempts
        self.max_transaction_retries = max_transaction_retries
        self.lease_ttl = lease_ttl
        self.clock = clock or (lambda: datetime.now(UTC))
        self.sleep = sleep

    def ingest(
        self,
        data_source: DataSource,
        collector_name: str,
        records: list[RawRecordInput],
        *,
        idempotency_key: str | None = None,
        next_cursor: dict[str, Any] | None = None,
        dry_run: bool = False,
    ) -> IngestionResult:
        if dry_run:
            return self._dry_run(data_source.id, records)

        previous = self._completed_idempotent_run(idempotency_key)
        if previous is not None:
            return self._result_from_run(previous)

        lease_owner = uuid.uuid4()
        checkpoint = self._acquire_collector_lease(data_source.id, collector_name, lease_owner)
        try:
            return self._ingest_locked(
                data_source,
                collector_name,
                records,
                checkpoint=checkpoint,
                idempotency_key=idempotency_key,
                next_cursor=next_cursor,
            )
        finally:
            self._release_collector_lease(checkpoint.id, lease_owner)

    def _ingest_locked(
        self,
        data_source: DataSource,
        collector_name: str,
        records: list[RawRecordInput],
        *,
        checkpoint: CollectionCheckpoint,
        idempotency_key: str | None,
        next_cursor: dict[str, Any] | None,
    ) -> IngestionResult:
        run = self._start_or_resume_run(
            data_source,
            collector_name,
            len(records),
            idempotency_key,
            checkpoint,
        )
        for attempt in range(self.max_transaction_retries):
            try:
                return self._process_transaction(
                    run,
                    checkpoint,
                    records,
                    next_cursor=next_cursor,
                )
            except (IntegrityError, OperationalError) as exc:
                self.session.rollback()
                if not self._is_retryable_database_error(exc) or (
                    attempt + 1 >= self.max_transaction_retries
                ):
                    self._mark_run_failed(run.id, exc, FailureKind.TRANSIENT)
                    raise
                self.sleep(0.05 * (2**attempt))
                run = self._reload_run(run.id)
                checkpoint = self._get_or_create_checkpoint(run.data_source_id, run.collector_name)
            except BaseException as exc:
                self.session.rollback()
                self._mark_run_interrupted(run.id, exc)
                raise
        raise AssertionError("transaction retry loop exhausted unexpectedly")

    def _process_transaction(
        self,
        run: CollectionRun,
        checkpoint: CollectionCheckpoint,
        records: list[RawRecordInput],
        *,
        next_cursor: dict[str, Any] | None,
    ) -> IngestionResult:
        now = self.clock()
        stored = duplicates = 0
        for record in records:
            self._advisory_record_lock(run.data_source_id, record.external_id)
            if self._store_revision(run.data_source_id, record, now):
                stored += 1
            else:
                duplicates += 1

        run.records_stored = stored
        run.records_duplicate = duplicates
        run.records_failed = 0
        run.completed_at = self.clock()
        run.heartbeat_at = run.completed_at
        run.status = CollectionStatus.SUCCEEDED.value
        run.checkpoint_end = next_cursor
        run.failure_kind = None
        run.error_message = None

        checkpoint.cursor = next_cursor
        checkpoint.last_successful_run_id = run.id
        checkpoint.version += 1
        checkpoint.heartbeat_at = run.completed_at
        checkpoint.lease_expires_at = run.completed_at + self.lease_ttl
        self.session.commit()
        return self._result_from_run(run)

    def _store_revision(
        self,
        data_source_id: uuid.UUID,
        record: RawRecordInput,
        observed_at: datetime,
    ) -> bool:
        digest = canonical_payload_hash(record.payload)
        identity = self.session.scalar(
            select(SourceRecord).where(
                SourceRecord.data_source_id == data_source_id,
                SourceRecord.external_id == record.external_id,
            )
        )
        if identity is None:
            identity = SourceRecord(
                data_source_id=data_source_id,
                external_id=record.external_id,
                record_type=record.record_type,
                original_published_at=record.published_at,
                first_seen_at=observed_at,
                ingested_at=observed_at,
            )
            self.session.add(identity)
            self.session.flush()

        existing = self.session.scalar(
            select(RawSourceRecord).where(
                RawSourceRecord.source_record_id == identity.id,
                RawSourceRecord.content_hash == digest,
            )
        )
        if existing is not None:
            return False

        revision_number = (
            self.session.scalar(
                select(func.max(RawSourceRecord.revision_number)).where(
                    RawSourceRecord.source_record_id == identity.id
                )
            )
            or 0
        ) + 1
        self.session.add(
            RawSourceRecord(
                source_record_id=identity.id,
                revision_number=revision_number,
                data_source_id=data_source_id,
                external_id=record.external_id,
                record_type=record.record_type,
                canonical_url=record.canonical_url,
                published_at=record.published_at,
                first_seen_at=observed_at,
                ingested_at=observed_at,
                content_hash=digest,
                raw_payload=record.payload,
                processing_status=ProcessingStatus.PENDING.value,
            )
        )
        self.session.flush()
        return True

    def _dry_run(self, data_source_id: uuid.UUID, records: list[RawRecordInput]) -> IngestionResult:
        stored = duplicates = 0
        seen: set[tuple[str, str]] = set()
        for record in records:
            digest = canonical_payload_hash(record.payload)
            key = (record.external_id, digest)
            if key in seen:
                duplicates += 1
                continue
            seen.add(key)
            existing = self.session.scalar(
                select(RawSourceRecord.id).where(
                    RawSourceRecord.data_source_id == data_source_id,
                    RawSourceRecord.external_id == record.external_id,
                    RawSourceRecord.content_hash == digest,
                )
            )
            if existing is None:
                stored += 1
            else:
                duplicates += 1
        return IngestionResult(None, len(records), stored, duplicates, 0, dry_run=True)

    def _start_or_resume_run(
        self,
        data_source: DataSource,
        collector_name: str,
        records_seen: int,
        idempotency_key: str | None,
        checkpoint: CollectionCheckpoint,
    ) -> CollectionRun:
        run = (
            self.session.scalar(
                select(CollectionRun).where(CollectionRun.idempotency_key == idempotency_key)
            )
            if idempotency_key
            else None
        )
        now = self.clock()
        if run is None:
            run = CollectionRun(
                data_source_id=data_source.id,
                collector_name=collector_name,
                idempotency_key=idempotency_key,
                status=CollectionStatus.RUNNING.value,
                started_at=now,
                heartbeat_at=now,
                records_seen=records_seen,
                checkpoint_start=checkpoint.cursor,
            )
            self.session.add(run)
        else:
            run.status = CollectionStatus.RUNNING.value
            run.retry_count += 1
            run.heartbeat_at = now
            run.completed_at = None
            run.error_message = None
            run.failure_kind = None
        self.session.commit()
        return run

    def _get_or_create_checkpoint(
        self, data_source_id: uuid.UUID, collector_name: str
    ) -> CollectionCheckpoint:
        checkpoint = self.session.scalar(
            select(CollectionCheckpoint).where(
                CollectionCheckpoint.data_source_id == data_source_id,
                CollectionCheckpoint.collector_name == collector_name,
            )
        )
        if checkpoint is None:
            checkpoint = CollectionCheckpoint(
                data_source_id=data_source_id,
                collector_name=collector_name,
                version=0,
            )
            self.session.add(checkpoint)
            self.session.flush()
        return checkpoint

    def recover_interrupted_runs(self, *, stale_after: timedelta) -> int:
        now = self.clock()
        cutoff = now - stale_after
        runs = list(
            self.session.scalars(
                select(CollectionRun).where(
                    CollectionRun.status == CollectionStatus.RUNNING.value,
                    CollectionRun.heartbeat_at < cutoff,
                )
            )
        )
        for run in runs:
            run.status = CollectionStatus.INTERRUPTED.value
            run.completed_at = now
            run.error_message = "worker heartbeat expired; checkpoint was not advanced"
            run.failure_kind = FailureKind.TRANSIENT.value
        self.session.execute(
            update(CollectionCheckpoint)
            .where(CollectionCheckpoint.lease_expires_at < now)
            .values(lease_owner=None, lease_expires_at=None)
        )
        self.session.commit()
        return len(runs)

    def mark_processing_failed(
        self, record: RawSourceRecord, error: Exception, *, permanent: bool = False
    ) -> None:
        record.attempt_count += 1
        record.last_error = str(error)
        if permanent or record.attempt_count >= self.max_attempts:
            record.processing_status = ProcessingStatus.PERMANENT_FAILURE.value
            record.next_retry_at = None
        else:
            record.processing_status = ProcessingStatus.RETRY_SCHEDULED.value
            record.next_retry_at = self.clock() + timedelta(minutes=2**record.attempt_count)
        self.session.commit()

    def _completed_idempotent_run(self, key: str | None) -> CollectionRun | None:
        if key is None:
            return None
        run = self.session.scalar(select(CollectionRun).where(CollectionRun.idempotency_key == key))
        if run is not None and run.status == CollectionStatus.SUCCEEDED.value:
            return run
        return None

    def _result_from_run(self, run: CollectionRun) -> IngestionResult:
        return IngestionResult(
            run.id,
            run.records_seen,
            run.records_stored,
            run.records_duplicate,
            run.records_failed,
            dry_run=run.dry_run,
            checkpoint=run.checkpoint_end,
        )

    def _reload_run(self, run_id: uuid.UUID) -> CollectionRun:
        run = self.session.get(CollectionRun, run_id)
        if run is None:
            raise RuntimeError("collection run disappeared")
        return run

    def _mark_run_failed(self, run_id: uuid.UUID, error: BaseException, kind: FailureKind) -> None:
        run = self._reload_run(run_id)
        run.status = CollectionStatus.FAILED.value
        run.completed_at = self.clock()
        run.heartbeat_at = run.completed_at
        run.error_message = str(error)
        run.failure_kind = kind.value
        self.session.commit()

    def _mark_run_interrupted(self, run_id: uuid.UUID, error: BaseException) -> None:
        run = self._reload_run(run_id)
        run.status = CollectionStatus.INTERRUPTED.value
        run.completed_at = self.clock()
        run.heartbeat_at = run.completed_at
        run.error_message = str(error)
        run.failure_kind = FailureKind.TRANSIENT.value
        self.session.commit()

    def _acquire_collector_lease(
        self,
        data_source_id: uuid.UUID,
        collector_name: str,
        owner: uuid.UUID,
    ) -> CollectionCheckpoint:
        if self.session.bind is not None and self.session.bind.dialect.name == "postgresql":
            self.session.execute(
                postgresql_insert(CollectionCheckpoint)
                .values(
                    id=uuid.uuid4(),
                    data_source_id=data_source_id,
                    collector_name=collector_name,
                    version=0,
                )
                .on_conflict_do_nothing(index_elements=["data_source_id", "collector_name"])
            )
            self.session.commit()
        else:
            self._get_or_create_checkpoint(data_source_id, collector_name)
            self.session.commit()

        checkpoint = self._get_or_create_checkpoint(data_source_id, collector_name)
        now = self.clock()
        result = self.session.execute(
            update(CollectionCheckpoint)
            .where(
                CollectionCheckpoint.id == checkpoint.id,
                or_(
                    CollectionCheckpoint.lease_owner.is_(None),
                    CollectionCheckpoint.lease_expires_at < now,
                ),
            )
            .values(
                lease_owner=owner,
                lease_expires_at=now + self.lease_ttl,
                heartbeat_at=now,
            )
        )
        if getattr(result, "rowcount", 0) != 1:
            self.session.rollback()
            raise CollectionAlreadyRunningError(
                f"collector {collector_name!r} is already running for this data source"
            )
        self.session.commit()
        return self._get_or_create_checkpoint(data_source_id, collector_name)

    def _release_collector_lease(self, checkpoint_id: uuid.UUID, owner: uuid.UUID) -> None:
        self.session.execute(
            update(CollectionCheckpoint)
            .where(
                CollectionCheckpoint.id == checkpoint_id,
                CollectionCheckpoint.lease_owner == owner,
            )
            .values(lease_owner=None, lease_expires_at=None)
        )
        self.session.commit()

    def _advisory_record_lock(self, data_source_id: uuid.UUID, external_id: str) -> None:
        if self.session.bind is None or self.session.bind.dialect.name != "postgresql":
            return
        key = f"source:{data_source_id}:{external_id}"
        self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))").bindparams(key=key)
        )

    @staticmethod
    def _is_retryable_database_error(error: DBAPIError) -> bool:
        sqlstate = getattr(error.orig, "sqlstate", None) or getattr(error.orig, "pgcode", None)
        return sqlstate in RETRYABLE_SQLSTATES
