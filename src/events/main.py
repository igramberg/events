from __future__ import annotations

import os
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from threading import Lock
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from events.domain import week_window_for
from events.storage import StorageRepository, build_sqlite_repository
from events.web import build_weekly_page_view

LOCAL_TZ = ZoneInfo("America/New_York")
TEMPLATES = Jinja2Templates(
    directory=str(Path(__file__).with_name("templates"))
)


def _default_now_provider() -> datetime:
    return datetime.now(LOCAL_TZ)


def _default_database_path() -> Path:
    if sys.platform == "darwin":
        return (
            Path.home()
            / "Library"
            / "Application Support"
            / "events"
            / "events.db"
        )
    if sys.platform == "win32":
        appdata = Path(
            os.environ.get(
                "APPDATA", Path.home() / "AppData" / "Roaming"
            )
        )
        return appdata / "events" / "events.db"
    state_home = Path(
        os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")
    )
    return state_home / "events" / "events.db"


def _default_database_url() -> str:
    configured_url = os.environ.get("EVENTS_DATABASE_URL")
    if configured_url:
        return configured_url
    database_path = str(_default_database_path()).replace("\\", "/")
    return f"sqlite+pysqlite:///{database_path}"


def _ensure_sqlite_parent_dir(database_url: str) -> None:
    prefixes = ("sqlite+pysqlite:///", "sqlite:///")
    prefix = next(
        (candidate for candidate in prefixes if database_url.startswith(candidate)),
        None,
    )
    if prefix is None:
        return
    database_path = Path(database_url.removeprefix(prefix))
    if database_path.name == ":memory:":
        return
    database_path.parent.mkdir(parents=True, exist_ok=True)


def _default_repository():
    database_url = _default_database_url()
    _ensure_sqlite_parent_dir(database_url)
    return build_sqlite_repository(database_url)


NowProvider = Callable[[], datetime]


def create_app(
    *,
    repository: StorageRepository | None = None,
    now_provider: NowProvider | None = None,
) -> FastAPI:
    app = FastAPI(title="events")
    repository_impl = repository
    repository_lock = Lock()
    now_provider_impl = now_provider or _default_now_provider

    def get_repository() -> StorageRepository:
        nonlocal repository_impl
        if repository_impl is None:
            with repository_lock:
                if repository_impl is None:
                    repository_impl = _default_repository()
        return repository_impl

    @app.get("/", response_class=HTMLResponse)
    def root(request: Request):
        window = week_window_for(now_provider_impl())
        events = get_repository().get_events_for_window(window)
        page = build_weekly_page_view(events=events, window=window)
        return TEMPLATES.TemplateResponse(
            request,
            "weekly_page.html",
            {"page": page},
        )

    return app


app = create_app()
