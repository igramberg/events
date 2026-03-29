# T4: Storage Layer for Current-Week Events

## TL;DR
T4 implements the persistent store for the canonical `Event` model. It stores the current week from the latest successful refresh (Monday–Monday, `America/New_York`), upserts by stable `event_key`, and exposes a repository contract so the web layer and refresh orchestration depend on an interface rather than raw SQL. The repository can technically query any `WeekWindow`, but only one window (the current week) is supported in production; other windows are for tests/debugging. Pruning runs only after a successful refresh to avoid wiping good rows on partial failures.

## Purpose
This document captures the design and execution plan for Task 4.

The storage layer sits between the canonical domain (`events.domain`) and the UI/refresh orchestration. Its goals are to:
- persist normalized `Event` instances that can be rendered in the weekly view,
- keep only the current week plus the most recently refreshed rows,
- expose a stable interface for upserting, querying, and pruning, and
- shield the rest of the app from SQLite-specific details.

## Objective
Build a storage subsystem that can be executed as part of the manual refresh flow:
1. Accept a batch of domain `Event`s from parser/orchestration code.
2. Upsert them into SQLite by `event_key`, recording when each row was last seen.
3. Allow the web UI to query the stored rows for an arbitrary `WeekWindow` (the current week by default).
4. Prune rows that are either outside the requested `WeekWindow` or were not seen on the most recent refresh.

Deliverables for T4 should make it possible for T7 (manual refresh) to update stored events without re-deriving schema or writing SQL inline.

## Business-Domain Decisions

### Scope Decisions
| Area | Decision | Notes |
| --- | --- | --- |
| Persistence target | SQLite current-week store | V0 runs locally; SQLite keeps dependencies small and offline-friendly |
| Data window | One authoritative week per [`WeekWindow`](./t2-domain-model.md) | Monday 00:00 (America/New_York) through next Monday 00:00 |
| Deduplication | Upsert by `event_key` only | Cross-source dedupe is out of scope for T4; identity collisions are surfaced later |
| Retention policy | Prune rows not seen during the latest successful refresh or falling outside the week | `last_seen_at` tracks refresh cycles so missing events disappear after a successful refresh |
| Category filtering | Storage stores a record’s `category` but does not enforce category scopes | Filtering happens in the web layer using `EventCategory.v0_categories()` |

### Boundary Decisions
| Decision | Direction |
| --- | --- |
| Storage domain | Maps canonical `Event` objects to SQLite rows | Tables are row-level projections of domain fields, not raw source documents |
| Repository contract | Provides `upsert_events`, `get_events_for_window`, and `prune_stale_events` | Web/orchestration depends on the interface instead of SQL strings |
| Time handling | Always store UTC timestamps (ISO format) for `starts_at` and `last_seen_at` | Repository converts `WeekWindow` start/end (local) via `utc_bounds_for_window(window)` → `(start_utc, end_utc)` in canonical `YYYY-MM-DDTHH:MM:SSZ`, start inclusive/end exclusive, DST-safe from `America/New_York`, and filters on `starts_at` in SQL (uses index); converts back to local only for display |
| Schema ownership | Storage package owns schema migrations and SQLAlchemy metadata | Application wiring relies on repository factories, not inline `CREATE TABLE` statements |

### Key Tradeoffs
| Decision | Chosen Direction | Pros | Cons |
| --- | --- | --- | --- |
| SQL library | SQLAlchemy 2.x Core + typing helpers | SQLAlchemy keeps the schema declarative, supports in-memory SQLite for tests, and is future-proof | Adds a dependency; increases surface area for future developers |
| Structured columns | Use JSON blobs for `identity_inputs`, `performers`, and `tags` | Keeps schema stable even if identity inputs gain new keys or arrays grow | Querying nested fields is harder; but storage only reads entire blobs |
| Pruning trigger | Explicit `prune_stale_events` call after each successful refresh | Clear lifecycle and easy to test | Requires the orchestrator to remember to call it, but that is part of the manual refresh choreography |

## Technical Design

### Architecture Overview
The storage package exposes a `StorageRepository` abstraction backed by a SQLAlchemy `CurrentWeekEvents` table. The repository:
1. Converts domain `Event` instances into flattened `EventRecord` dataclasses (lossless for every `identity_kind`).
2. Executes an upsert keyed on `event_key` using `ON CONFLICT(event_key) DO UPDATE` that replaces mutable fields (title/category/description/organizer/performers/tags/etc.) but rejects changes to identity material (`identity_kind`, `identity_inputs`) for an existing key (raises, leaves the row unchanged, and should cause the refresh to be treated as failed so prune is skipped).
3. Tags each row with `last_seen_at` (UTC) set to the refresh timestamp provided by the caller.
4. Queries rows whose `starts_at` falls within a supplied `WeekWindow` using `utc_bounds_for_window(window)` (start inclusive/end exclusive) to produce canonical UTC strings and filtering in SQL on `starts_at` (indexable), then returns results sorted as specified.
5. Deletes rows whose `last_seen_at` is older than the last refresh or whose `starts_at` lies outside the requested window using the same `utc_bounds_for_window(window)` filtering as reads (start inclusive, end exclusive).

The web layer uses the repository to power the weekly list endpoint. Manual refresh orchestration calls `upsert_events()` and then `prune_stale_events()` before reporting success.

### Schema Blueprint
Table `current_week_events` (name chosen to make scope explicit).

| Column | Type | Constraints | Notes |
| --- | --- | --- | --- |
| `event_key` | `TEXT` | `PRIMARY KEY` | Domain-stable identifier; same format as `Event.event_key`. |
| `identity_kind` | `TEXT` | NOT NULL | Literal from `IdentityKind`. |
| `identity_inputs` | `JSON` (`TEXT` in SQLite) | NOT NULL | Stored as canonical JSON string (`json.dumps(..., sort_keys=True, separators=(',', ':'), ensure_ascii=False)`), exactly matching the domain `identity_inputs` for all `identity_kind` branches; validation is application-side because SQLite treats JSON as TEXT. |
| `title` | `TEXT` | NOT NULL | Display title. |
| `category` | `TEXT` | NOT NULL | Value from `EventCategory`. |
| `venue_key` | `TEXT` | NOT NULL | Domain venue key. |
| `venue_name` | `TEXT` | NOT NULL | Display name. |
| `location_key` | `TEXT` | NOT NULL | Domain location key. |
| `city` | `TEXT` | NOT NULL | Display city. |
| `region` | `TEXT` | NOT NULL | Display region. |
| `country_code` | `TEXT` | NOT NULL | Display country code. |
| `organizer_key` | `TEXT` | NULLABLE | Optional organizer identity (must be null when `organizer_name` is null, and vice versa). |
| `organizer_name` | `TEXT` | NULLABLE | Display organizer label (must be null when `organizer_key` is null). |
| `starts_at` | `TEXT` | NOT NULL | ISO 8601 UTC timestamp, required fixed-width `YYYY-MM-DDTHH:MM:SSZ` (same as `format_starts_at_utc`; second precision aligns with domain identity rules); we never store naive datetimes. |
| `source_url` | `TEXT` | NOT NULL | Provenance URL. |
| `source_name` | `TEXT` | NOT NULL | Source slug. |
| `source_event_id` | `TEXT` | NULLABLE | Optional source-native ID. |
| `description` | `TEXT` | NULLABLE | Optional rich text. |
| `performers` | `JSON` (`TEXT`) | NOT NULL DEFAULT `'[]'` | Stored as JSON array of strings; preserves insertion order; no dedupe. |
| `tags` | `JSON` (`TEXT`) | NOT NULL DEFAULT `'[]'` | Stored as JSON array of strings; preserves insertion order; no dedupe. |
| `last_seen_at` | `TEXT` | NOT NULL | UTC timestamp for the most recent refresh, required fixed-width format `YYYY-MM-DDTHH:MM:SS.ssssssZ` to keep lexicographic comparisons/indexes valid; matches `refresh_timestamp` format. Non-canonical strings must be rejected. |

Indexes:
- Primary key on `event_key` ensures deterministic upserts.
- Index on `starts_at` accelerates week-window queries (lexicographic order relies on the documented ISO format).
- Index on `last_seen_at` helps pruning (lexicographic order relies on the documented ISO format).
- No indexes on `category` or `source_name` for V0; add later if UI/refresh starts filtering by them.

### Repository Contract
Expose an abstract `StorageRepository` with these methods:

```python
class StorageRepository(Protocol):
    def upsert_events(
        self,
        events: Sequence[Event],
        refresh_timestamp: datetime,
    ) -> None:
        ...

    def get_events_for_window(
        self,
        window: WeekWindow,
    ) -> Sequence[Event]:
        ...

    def prune_stale_events(
        self,
        window: WeekWindow,
        refresh_timestamp: datetime,
    ) -> None:
        ...
```

- `refresh_timestamp` is the refresh start time supplied by the orchestrator; it must be a timezone-aware UTC `datetime` (naive or non-UTC values are rejected). The repository always serializes it via `strftime('%Y-%m-%dT%H:%M:%S.%fZ')` (fixed-width microseconds); stored strings must match exactly. `upsert_events` and `prune_stale_events` must receive the same value, even if the refresh spans midnight. (Optional) `refresh_id` may be supplied for stricter ordering if concurrent refreshes are ever allowed.
- `upsert_events` writes each event row inside a single transaction per call, performs `ON CONFLICT DO UPDATE` (identity material must match existing row; mismatch raises, rolls back the batch, and leaves existing rows unchanged), and sets `last_seen_at = refresh_timestamp`.
- `get_events_for_window` reads rows whose `starts_at` falls inside `window` by filtering in SQL on UTC string bounds and returns results sorted by `starts_at` ascending, then `venue_name`, then `event_key`.
- `prune_stale_events` deletes rows whose `last_seen_at < refresh_timestamp` (meaning they were missing in the current refresh) *or* whose `starts_at` is outside `window` using `utc_bounds_for_window(window)` (start inclusive, end exclusive) and comparing in SQL. If any upsert raises (e.g., identity mismatch), the refresh is considered failed/partial and `prune_stale_events` must be skipped.

The concrete repository will use SQLAlchemy Core metadata plus `text` serialization helpers for JSON columns.

### Current-Week Flow
Manual refresh orchestration will:
1. Compute the authoritative `WeekWindow` (`week_window_for(datetime.now(tz=UTC))`; Monday-based in `America/New_York`). Callers may supply any `WeekWindow`, but production use remains Monday-based and only one active window is supported at a time.
2. Capture `refresh_started_at` once (tz-aware UTC, high-resolution) and pass it to both `upsert_events(events, refresh_started_at)` and `prune_stale_events(window, refresh_started_at)`.
3. Call `prune_stale_events(window, refresh_started_at)` once all candidates have been processed and the refresh has succeeded; skip if any upsert raised (e.g., identity mismatch) or if the refresh is partial/failed to avoid data loss. A successful refresh implies the upsert batch completed in one transaction.
4. Query `get_events_for_window(window)` when rendering the UI.

Keeping a single `refresh_started_at` timestamp ensures `last_seen_at` comparisons are stable even if a refresh spans midnight or a DST transition.

### Transaction and Consistency Expectations
- V0 can run `upsert_events` and `prune_stale_events` in separate transactions; no cross-call transaction requirement. If a refresh crashes after `upsert_events` commits but before prune, readers may briefly see a pre-prune superset until the next successful refresh prunes it; acceptable for V0.
- A future improvement may wrap a refresh in one transaction to avoid mixed-state reads; optional, not required for V0 manual refresh. Callers that need stronger consistency can wrap both calls in one transaction.

### Migration and Configuration
- The repository will expose a `create_tables(engine)` helper to initialize the schema (for both tests and the local SQLite file).
- For now, migrations are manual: the schema creation lives in Python code rather than Alembic, but the metadata is explicit so future migration tooling can be layered on top.
- SQLite JSON is stored as TEXT; validation happens in application code. WAL/synchronous tuning is deferred; defaults are acceptable for V0, and tuning can be added if refresh/UI throughput requires it.

### Active Window Assumption
- Only one authoritative `WeekWindow` (the current week) should be live in production. Other windows are intended for tests or one-off diagnostics. Pruning outside the active window will remove rows even if another component previously queried a different window.

## Implementation Plan
1. Add the SQLAlchemy dependency and create the `storage` package skeleton.
2. Define `EventRecord`, table metadata, and serialization helpers for `identity_inputs`, `performers`, and `tags`.
3. Implement `SqliteStorageRepository` that wires into FastAPI (or CLI) later, exposes `StorageRepository`, and can be instantiated with an `Engine`.
4. Add repository unit tests that drive an in-memory SQLite engine through upsert/query/prune flows.

## Test Plan
- `test_storage_repository_upsert_and_query`: Upserting the same `event_key` twice updates mutable fields (e.g., changed title) and does not duplicate rows.
- `test_storage_repository_round_trip_fields`: `performers`, `tags`, and `description` survive a write/read cycle.
- `test_storage_repository_identity_round_trip`: `identity_inputs` remains lossless for each `identity_kind` branch.
- `test_storage_repository_prune_missing`: Rows not upserted during the latest successful refresh are deleted after `prune_stale_events`.
- `test_storage_repository_prune_by_window`: An event outside the `WeekWindow` is pruned even if `last_seen_at` matches; build the window in `America/New_York`, convert bounds to UTC strings, and verify SQL filtering handles DST/weekly boundaries.
- `test_storage_repository_week_window_filtering`: Events exactly on window edges are included/excluded using the same logic as `event_in_week_window`.
- `test_storage_repository_rejects_naive_refresh_timestamp`: Repository raises or rejects naive datetimes passed as `refresh_timestamp` and any non-canonical string formatting.

Tests should rely on in-memory SQLite engines created per test and the SQLAlchemy metadata defined in this package.

## Exit Criteria
- The repository exposes a documented interface for upsert/query/prune flows.
- Schema metadata and helper functions live in `src/events/storage` and can be initialized programmatically.
- At least one integration-style test ensures an `Event` serialized to the database can be read back intact for the current week.
- The manual refresh orchestration can depend on the storage package without touching SQL strings.
