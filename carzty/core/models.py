##xchronusx
"""
carzty.core.models - what a task actually is.

Synopsis:
    Task dataclass + the three states a task can be in.

Description:
    Every time in here is a plain int of epoch seconds in UTC. Timezones only
    matter when a human types a time or when a daily schedule has to survive
    daylight saving, and that's handled in engine.py using the task's `tz`.

    pending      = a reminder went off and you haven't hit Done yet
    followup_at  = when the next nag (or snooze) goes off
    next_due     = the next regularly scheduled reminder

Notes:
    Author: Zachary Wright (xchronusx)
    If you add a field here, add it to store.py too or it won't get saved. Ask me how I know.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from zoneinfo import ZoneInfo

ACTIVE = "active"
PAUSED = "paused"
DONE = "done"

DELIVER_DM = "dm"
DELIVER_CHANNEL = "channel"


@lru_cache(maxsize=256)
def get_zone(name: str) -> ZoneInfo:
    return ZoneInfo(name)


@dataclass(frozen=True)
class Task:
    user_id: int
    title: str
    tz: str
    created_at: int

    id: int | None = None
    notes: str | None = None

    # schedule. both None = one-shot
    interval_seconds: int | None = None
    weekdays: tuple[int, ...] | None = None

    next_due: int | None = None
    nag_seconds: int | None = None
    followup_at: int | None = None
    followup_kind: str | None = None  # "nag" | "snooze"

    pending: bool = False
    nag_count: int = 0
    state: str = ACTIVE

    deliver: str = DELIVER_DM
    guild_id: int | None = None
    channel_id: int | None = None

    last_fired_at: int | None = None
    last_done_at: int | None = None
    times_fired: int = 0
    times_done: int = 0
    streak: int = 0

    last_message_id: int | None = None
    last_message_channel_id: int | None = None
    last_error: str | None = None

    @property
    def recurring(self) -> bool:
        return bool(self.interval_seconds) or bool(self.weekdays)

    @property
    def zone(self) -> ZoneInfo:
        return get_zone(self.tz)
##xchronusx
