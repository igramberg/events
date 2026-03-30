# events

Local web app for assembling a weekly list of greater Boston events from official venue and organization sources.

## Scope

The product focus is a single weekly view of upcoming events in the greater Boston area.

V0 includes:

- concerts and live music
- theater and performing arts
- manual refresh
- current-week storage only

Deferred phases include:

- exhibitions
- museum special-night events
- film screenings
- automated scheduled refresh

## Architecture

- Backend: FastAPI
- Storage: SQLite
- Rendering: server-side HTML templates
- Source strategy: official sources first, generic structured-data parsing before venue-specific fallbacks

See [docs/architecture.md](docs/architecture.md) for the program-level design.

## Development

Task execution is intentionally phased:

1. Repo bootstrap and architecture
2. Core event model and inclusion rules
3. Source adapter framework and generic parser
4. Storage for current-week events
5. Web UI shell
6. Initial source pack for music and theater
7. Manual refresh
8. Scheduler

### Tooling

- Package manager: `uv` (lockfile committed as `uv.lock`)
- Lint/format: `ruff` (80-column line length)

```bash
# Setup (creates .venv/)
uv sync --extra dev

# Tests
uv run pytest

# Lint + format
uv run ruff check . --fix
uv run ruff format .

# Run the web UI
uv run uvicorn events.main:app --reload

# Default SQLite location:
# macOS: ~/Library/Application Support/events/events.db
# Linux: ~/.local/state/events/events.db
# Windows: %APPDATA%/events/events.db
#
# Optional: override the default SQLite location
EVENTS_DATABASE_URL=sqlite+pysqlite:////tmp/events.db uv run uvicorn events.main:app --reload
```
