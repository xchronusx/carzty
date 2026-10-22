##xchronusx
"""
tests/conftest.py - shared fixtures. frozen time, a throwaway database, a task factory.

Notes:
    Author: Zachary Wright (xchronusx)
    "now" in these tests is Wed 2026-10-21 20:00 in Phoenix (03:00 UTC Thursday). Phoenix has no DST,
    which is why it's the default. New York gets dragged in for the DST tests because of course it does.
"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from carzty.core.models import Task
from carzty.core.store import Store

PHX = ZoneInfo("America/Phoenix")
NYC = ZoneInfo("America/New_York")

NOW_DT = datetime(2026, 10, 21, 20, 0, tzinfo=PHX)
NOW = int(NOW_DT.timestamp())


def local(y, mo, d, h=0, mi=0, tz=PHX) -> int:
    return int(datetime(y, mo, d, h, mi, tzinfo=tz).timestamp())


def as_local(ts: int, tz=PHX) -> datetime:
    return datetime.fromtimestamp(ts, tz)


@pytest.fixture
def now() -> int:
    return NOW


@pytest.fixture
def now_dt() -> datetime:
    return NOW_DT.astimezone(timezone.utc)


@pytest.fixture
def make_task():
    def _make(**kw) -> Task:
        base = dict(user_id=111, title="drink water", tz="America/Phoenix", created_at=NOW)
        base.update(kw)
        return Task(**base)

    return _make


@pytest.fixture
def store():
    s = Store(":memory:")
    yield s
    s.close()
##xchronusx
