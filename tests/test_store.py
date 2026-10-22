##xchronusx
"""
tests/test_store.py - sqlite in, sqlite out, nothing lost in between.

Notes:
    Author: Zachary Wright (xchronusx)
"""

from __future__ import annotations

from dataclasses import replace

from carzty.core.models import DONE, PAUSED
from carzty.core.store import Store
from tests.conftest import NOW


def test_roundtrip_keeps_every_field(store, make_task):
    t = make_task(
        notes="the big bottle",
        weekdays=(0, 2, 4),
        next_due=NOW + 60,
        nag_seconds=600,
        pending=True,
        followup_at=NOW + 600,
        followup_kind="nag",
        deliver="channel",
        guild_id=42,
        channel_id=4242,
        streak=3,
        last_error="whoops",
    )
    saved = store.add(t)
    assert saved.id is not None
    assert replace(saved, id=None) == t


def test_save_updates(store, make_task):
    t = store.add(make_task(next_due=NOW))
    store.save(replace(t, title="drink MORE water", pending=True), NOW)
    got = store.get(t.id)
    assert got.title == "drink MORE water" and got.pending is True


def test_users_cant_touch_each_other(store, make_task):
    mine = store.add(make_task(user_id=1))
    assert store.get_for_user(mine.id, 2) is None
    assert store.delete(mine.id, 2) is False
    assert store.get(mine.id) is not None
    assert store.delete(mine.id, 1) is True


def test_due_query(store, make_task):
    a = store.add(make_task(next_due=NOW - 5))
    b = store.add(make_task(next_due=NOW + 500))
    c = store.add(make_task(next_due=NOW + 500, followup_at=NOW - 1, pending=True))
    store.add(make_task(next_due=NOW - 5, state=PAUSED))
    store.add(make_task(next_due=NOW - 5, state=DONE))
    ids = {t.id for t in store.due(NOW)}
    assert ids == {a.id, c.id}
    assert b.id not in ids


def test_list_and_count(store, make_task):
    store.add(make_task(next_due=NOW + 100))
    store.add(make_task(next_due=NOW + 50, pending=True))
    store.add(make_task(state=DONE))
    store.add(make_task(user_id=999, next_due=NOW))
    listed = store.list_for_user(111)
    assert len(listed) == 2 and listed[0].pending  # ringing stuff first
    assert len(store.list_for_user(111, include_done=True)) == 3
    assert store.count_open(111) == 2


def test_search_escapes_like_wildcards(store, make_task):
    store.add(make_task(title="100% done"))
    store.add(make_task(title="1000 pushups"))
    assert [t.title for t in store.search_for_user(111, "100%")] == ["100% done"]
    t = store.add(make_task(title="other"))
    assert [x.id for x in store.search_for_user(111, f"#{t.id}")] == [t.id]


def test_purge_done(store, make_task):
    old = store.add(make_task(state=DONE, last_done_at=NOW - 40 * 86400))
    fresh = store.add(make_task(state=DONE, last_done_at=NOW - 86400))
    assert store.purge_done(NOW - 30 * 86400) == 1
    assert store.get(old.id) is None and store.get(fresh.id) is not None


def test_users_and_meta(store):
    assert store.get_user(5) == {"tz": None, "tone": None}
    store.set_user(5, NOW, tz="Europe/London")
    store.set_user(5, NOW, tone="chill")
    assert store.get_user(5) == {"tz": "Europe/London", "tone": "chill"}
    store.set_meta("k", "v1")
    store.set_meta("k", "v2")
    assert store.get_meta("k") == "v2"
    assert store.get_meta("missing") is None


def test_migrations_are_idempotent(tmp_path, make_task):
    path = tmp_path / "sub" / "carzty.db"
    s1 = Store(path)
    s1.add(make_task())
    v = s1.schema_version
    s1.close()
    s2 = Store(path)  # reopening shouldn't re-run anything or lose data
    assert s2.schema_version == v
    assert s2.stats()["total"] == 1
    s2.close()
##xchronusx
