from __future__ import annotations

from datetime import datetime
from typing import Protocol, Sequence

from events.domain import WeekWindow
from events.domain.models import Event


class StorageRepository(Protocol):
    def upsert_events(
        self, events: Sequence[Event], refresh_timestamp: datetime
    ) -> None: ...

    def get_events_for_window(self, window: WeekWindow) -> Sequence[Event]: ...

    def prune_stale_events(
        self, window: WeekWindow, refresh_timestamp: datetime
    ) -> None: ...
