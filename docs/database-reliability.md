# Database and ingestion reliability

## Source identity and immutable revisions

`source_records` owns the stable provider key `(data_source_id, external_id)` and preserves the
original `published_at` equivalent, `first_seen_at`, and `ingested_at`. The existing
`raw_source_records` table now stores immutable revisions:

- `(source_record_id, revision_number)` is unique and orders revisions.
- `(source_record_id, content_hash)` is unique and makes identical ingestion a no-op.
- `first_seen_at` on a revision is its actual availability time inside MarketMind.
- Latest retrieval orders by revision number.
- Historical as-of retrieval selects the newest revision whose `first_seen_at` is not later than
  the requested time.

Event provenance continues to reference `raw_source_records.id`, so an event points to an exact
immutable revision rather than a mutable provider identity.

## Concurrency strategy

Correctness has two database boundaries:

1. A collector obtains an expiring row lease on its unique
   `(data_source_id, collector_name)` checkpoint. An atomic conditional update prevents overlapping
   workers from advancing the same cursor.
2. Inside the ingestion transaction, PostgreSQL `pg_advisory_xact_lock` serializes work for one
   provider/external-ID key. The lock ends automatically on commit or rollback.

The unique identity, content-hash, and revision-number constraints remain the final correctness
boundary. Serialization failures, deadlocks, and uniqueness races are retried with bounded
exponential backoff. The full record batch and cursor advance commit together.

## Collector recovery

A collection run is persisted before its evidence transaction starts. The starting cursor is
recorded on the run. Evidence revisions and the ending cursor then commit atomically:

- Success advances the checkpoint and increments its version.
- An exception rolls back all revisions from that batch, marks the run `interrupted`, and leaves
  the checkpoint unchanged.
- A repeated successful idempotency key returns the stored run result without new writes.
- Expired heartbeats can be marked interrupted and expired leases cleared.
- Transient processing failures schedule exponential backoff.
- Permanent failures enter `permanent_failure` and are never scheduled automatically.
- Dry-run mode validates typed fixtures and reports inserts/no-ops without writing runs, records, or
  checkpoints.

Leases default to 15 minutes. M0B should add heartbeat renewal if a single provider page can take
longer than the lease.

## Migrations

`0002_ingestion_reliability`:

- creates stable `source_records` identities;
- backfills each M0A raw record as revision 1 without changing its evidence timestamps;
- replaces the old provider/external-ID uniqueness on raw records with revision uniqueness;
- adds run idempotency, checkpoint snapshots, heartbeat, dry-run, and failure classification fields;
- creates durable collection checkpoints and lease fields.

Downgrading to M0A is necessarily lossy because M0A cannot represent multiple revisions. The
downgrade retains revision 1 and removes later revisions after removing their event links.

## PostgreSQL verification

Set `TEST_POSTGRES_URL` to a dedicated disposable database:

```bash
TEST_POSTGRES_URL=postgresql+psycopg://user@localhost:55432/marketmind_test \
  uv run pytest -m postgresql -vv
```

The PostgreSQL suite performs downgrade, upgrade, downgrade, and re-upgrade; runs Alembic's schema
drift check; inspects constraints and indexes; tests concurrent identical ingestion; tests
concurrent different revisions; and verifies collector lease exclusion. Never point this test at a
database containing data: the fixture downgrades and truncates the configured database.

The normal SQLite suite remains useful for fast application tests but is not evidence of
PostgreSQL-specific correctness.

