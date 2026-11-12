# Architecture

## Direction of dependencies

```text
API / worker  ->  application services  ->  domain contracts
      |                    |
      +----------> infrastructure adapters
```

The domain package knows nothing about FastAPI, Celery, SQLAlchemy, or any provider. Application
services coordinate transactions and domain inputs. Infrastructure implements persistence and
offline collection. Transport layers translate HTTP or worker messages into application calls.

## Evidence and provenance

A source identity is identified by `(data_source_id, external_id)`. Its raw evidence is an
append-only sequence of revisions. A canonical SHA-256 payload hash makes identical re-ingestion a
no-op; changed content creates the next immutable revision. The original publication and
first-seen timestamps remain on the source identity, while each revision records its own
availability timestamps.

Financial events are separate, structured claims. The many-to-many `event_sources` table records
which source records support each event. This allows event logic to evolve without mutating source
evidence.

The three relevant clocks remain distinct:

- `published_at`: when the provider says the information became public.
- `first_seen_at`: when MarketMind first observed it.
- `ingested_at`: when the record entered durable storage.

## Provider boundaries

`MarketDataCollector`, `FinancialNewsCollector`, and `SecFilingCollector` are independent
protocols even though they currently share a neutral raw-record shape. This avoids coupling
application logic to an eventual vendor SDK. `InferenceGateway` similarly keeps AI extraction
replaceable; M0A contains no implementation.

## Processing lifecycle

Raw records use explicit `pending`, `processing`, `succeeded`, `retry_scheduled`, and
`permanent_failure` states. Attempts, the next retry time, and the last error are stored on the evidence
record. Collection runs retain aggregate counts and errors so partial outcomes are observable.
Collection checkpoints store durable cursors. Expiring database leases prevent two workers from
advancing the same collector checkpoint, and PostgreSQL transaction advisory locks serialize
revision assignment for one provider record. Scheduling remains deferred to M0B.

## Design concerns for M0B

1. Decide provider-specific canonicalization rules before external payloads are hashed; semantically
   identical payloads with unstable metadata could otherwise create unnecessary revisions.
2. Choose lease durations and collection page sizes from observed provider latency, and add active
   heartbeat renewal if one page can exceed the configured lease TTL.
3. Decide event identity rules across extractors before automated extraction begins. The current
   globally unique external event ID expects an application-owned stable key.
4. Define retention, compression, and object-storage thresholds for large filing bodies.
5. Add authentication and authorization before exposing non-local environments.
6. Add tracing and metrics around collection, queues, and inference cost before scheduled work.


