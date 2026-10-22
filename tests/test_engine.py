##xchronusx
"""
tests/test_engine.py - the scheduling brain. if these pass, the yelling happens on time.

Notes:
    Author: Zachary Wright (xchronusx)
    Time is fake in here. Every test passes `now` explicitly, so nothing depends on when you run it.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from carzty.core import engine
from carzty.core.engine import EngineError
from carzty.core.models import ACTIVE, DONE, PAUSED
from carzty.core.timeparse import DAY, HOUR, MINUTE, Schedule
from tests.conftest import NOW, NYC, PHX, as_local, local

#region OCCURRENCES


def test_interval_fires_and_advances(make_task):
    t = make_task(interval_seconds=HOUR, next_due=NOW)
    t2, fired = engine.process(t, NOW)
    assert fired is not None and fired.kind == "scheduled"
    assert t2.next_due == NOW + HOUR
    assert t2.pending and t2.times_fired == 1


def test_not_due_yet_does_nothing(make_task):
    t = make_task(interval_seconds=HOUR, next_due=NOW + 5)
    t2, fired = engine.process(t, NOW)
    assert fired is None and t2 == t


def test_paused_and_done_never_fire(make_task):
    for state in (PAUSED, DONE):
        t = make_task(interval_seconds=HOUR, next_due=NOW - 100, state=state)
        assert engine.process(t, NOW)[1] is None


def test_offline_for_ages_fires_once_and_catches_up(make_task):
    # bot was off for 10.5 hours with an hourly task. one reminder, not ten.
    due = NOW - int(10.5 * HOUR)
    t = make_task(interval_seconds=HOUR, next_due=due)
    t2, fired = engine.process(t, NOW)
    assert fired.late_by == int(10.5 * HOUR)
    assert t2.next_due == due + 11 * HOUR
    assert NOW < t2.next_due <= NOW + HOUR
    # and the next tick doesn't fire again
    assert engine.process(t2, NOW + 1)[1] is None


def test_one_shot_fires_once(make_task):
    t = make_task(next_due=NOW)
    t2, fired = engine.process(t, NOW)
    assert fired.kind == "scheduled"
    assert t2.next_due is None and t2.pending
    assert engine.process(t2, NOW + DAY)[1] is None  # no nag, so it just sits there waiting for Done


def test_daily_keeps_wall_clock_across_dst(make_task):
    # new york falls back nov 1 2026. 9am should stay 9am, which means the UTC hour moves.
    due = local(2026, 10, 31, 9, tz=NYC)
    t = make_task(tz="America/New_York", interval_seconds=DAY, next_due=due)
    t2, _ = engine.process(t, due)
    t3, _ = engine.process(t2, t2.next_due)
    assert as_local(t2.next_due, NYC).hour == 9
    assert as_local(t3.next_due, NYC).hour == 9
    assert t3.next_due - t2.next_due == DAY  # nov 1 -> nov 2 is a normal day
    assert t2.next_due - due == DAY + HOUR  # oct 31 -> nov 1 is 25 hours long


def test_daily_catchup_after_long_outage_keeps_time(make_task):
    due = local(2026, 9, 1, 9, tz=NYC)  # bot's been dead since september, through a DST change
    now = local(2026, 11, 15, 12, tz=NYC)
    t = make_task(tz="America/New_York", interval_seconds=DAY, next_due=due)
    t2, fired = engine.process(t, now)
    assert fired is not None
    nxt = as_local(t2.next_due, NYC)
    assert (nxt.month, nxt.day, nxt.hour) == (11, 16, 9)


def test_weekly(make_task):
    due = local(2026, 10, 21, 9)
    t = make_task(interval_seconds=7 * DAY, next_due=due)
    t2, _ = engine.process(t, due)
    assert as_local(t2.next_due).day == 28


def test_weekdays_skip_the_weekend(make_task):
    fri = local(2026, 10, 23, 8, 45)
    t = make_task(weekdays=(0, 1, 2, 3, 4), next_due=fri)
    t2, fired = engine.process(t, fri)
    assert fired is not None
    nxt = as_local(t2.next_due)
    assert (nxt.weekday(), nxt.day, nxt.hour, nxt.minute) == (0, 26, 8, 45)


def test_weekday_set_wraps(make_task):
    thu = local(2026, 10, 22, 19)
    t = make_task(weekdays=(0, 3), next_due=thu)  # mon + thu
    t2, _ = engine.process(t, thu)
    assert as_local(t2.next_due).weekday() == 0
    t3, _ = engine.process(t2, t2.next_due)
    assert as_local(t3.next_due).weekday() == 3


def test_weekdays_long_outage(make_task):
    due = local(2026, 6, 1, 9)  # a monday in june
    t = make_task(weekdays=(2,), next_due=due)  # wednesdays only... someone typo'd the first due. align fixes it
    t = replace(t, next_due=engine.align_to_weekdays(due, (2,), PHX))
    t2, _ = engine.process(t, NOW)
    nxt = as_local(t2.next_due)
    assert nxt.weekday() == 2 and nxt.hour == 9 and t2.next_due > NOW


def test_first_due_variants():
    tz = PHX
    assert engine.first_due(Schedule(interval_seconds=HOUR), tz, NOW) == NOW + HOUR
    assert engine.first_due(Schedule(interval_seconds=HOUR), tz, NOW, when=NOW + 5) == NOW + 5
    with pytest.raises(EngineError):
        engine.first_due(Schedule(), tz, NOW)
    # weekdays with no time: next allowed day at 9am. it's wed 8pm, so thursday 9am
    got = as_local(engine.first_due(Schedule(weekdays=(0, 1, 2, 3, 4)), tz, NOW))
    assert (got.weekday(), got.hour) == (3, 9)
    # weekdays + when that lands on a saturday rolls to monday, same time
    sat = local(2026, 10, 24, 10)
    got = as_local(engine.first_due(Schedule(weekdays=(0, 1, 2, 3, 4)), tz, NOW, when=sat))
    assert (got.weekday(), got.hour, got.day) == (0, 10, 26)

#endregion


#region NAGGING


def test_nag_sequence_and_give_up(make_task):
    t = make_task(interval_seconds=DAY, next_due=NOW, nag_seconds=10 * MINUTE)
    t, fired = engine.process(t, NOW, max_nags=3)
    assert fired.kind == "scheduled" and t.followup_at == NOW + 10 * MINUTE

    now = NOW
    kinds = []
    for _ in range(3):
        now = t.followup_at
        t, fired = engine.process(t, now, max_nags=3)
        kinds.append((fired.kind, fired.nag_number, fired.gave_up))
    assert kinds == [("nag", 1, False), ("nag", 2, False), ("nag", 3, True)]
    assert t.followup_at is None and t.pending
    assert engine.process(t, now + HOUR, max_nags=3)[1] is None


def test_next_occurrence_supersedes_unacked(make_task):
    t = make_task(interval_seconds=HOUR, next_due=NOW, streak=5)
    t, _ = engine.process(t, NOW)
    t, fired = engine.process(t, NOW + HOUR)  # never hit Done
    assert fired.kind == "scheduled" and fired.missed_previous
    assert t.streak == 0


def test_scheduled_wins_over_followup(make_task):
    t = make_task(interval_seconds=HOUR, next_due=NOW, nag_seconds=HOUR)
    t, _ = engine.process(t, NOW)
    t, fired = engine.process(t, NOW + HOUR)  # nag and next occurrence land together
    assert fired.kind == "scheduled" and t.nag_count == 0

#endregion


#region ACTIONS


def test_done_while_ringing(make_task):
    t = make_task(interval_seconds=DAY, next_due=NOW, nag_seconds=5 * MINUTE)
    t, _ = engine.process(t, NOW)
    t2, outcome = engine.complete(t, NOW + 60)
    assert outcome == "acked"
    assert not t2.pending and t2.followup_at is None
    assert t2.next_due == NOW + DAY  # schedule untouched
    assert t2.times_done == 1 and t2.streak == 1


def test_done_early_skips_next(make_task):
    t = make_task(interval_seconds=DAY, next_due=NOW + HOUR)
    t2, outcome = engine.complete(t, NOW)
    assert outcome == "early"
    assert t2.next_due == NOW + HOUR + DAY


def test_done_one_shot(make_task):
    t = make_task(next_due=NOW + HOUR)
    t2, outcome = engine.complete(t, NOW)
    assert outcome == "finished" and t2.state == DONE and t2.next_due is None
    with pytest.raises(EngineError):
        engine.complete(t2, NOW)


def test_snooze_only_when_ringing(make_task):
    t = make_task(interval_seconds=DAY, next_due=NOW + HOUR)
    with pytest.raises(EngineError):
        engine.snooze(t, NOW, 900)


def test_snooze_then_nag_resumes(make_task):
    t = make_task(interval_seconds=DAY, next_due=NOW, nag_seconds=10 * MINUTE)
    t, _ = engine.process(t, NOW)
    t = engine.snooze(t, NOW + 60, HOUR)
    assert t.followup_kind == "snooze" and t.followup_at == NOW + 60 + HOUR
    assert engine.process(t, NOW + 30 * MINUTE)[1] is None  # snoozed, so the 10m nag doesn't fire
    t, fired = engine.process(t, NOW + 60 + HOUR)
    assert fired.kind == "snooze" and fired.nag_number == 0
    assert t.followup_kind == "nag" and t.followup_at == NOW + 60 + HOUR + 10 * MINUTE


def test_snooze_without_nag_fires_once(make_task):
    t = make_task(next_due=NOW)
    t, _ = engine.process(t, NOW)
    t = engine.snooze(t, NOW, 900)
    t, fired = engine.process(t, NOW + 900)
    assert fired.kind == "snooze" and not fired.gave_up
    assert t.followup_at is None and t.pending


def test_skip(make_task):
    t = make_task(interval_seconds=DAY, next_due=NOW + HOUR)
    t2, outcome = engine.skip(t, NOW)
    assert outcome == "skipped" and t2.next_due == NOW + HOUR + DAY

    ringing, _ = engine.process(replace(t, next_due=NOW), NOW)
    t3, outcome = engine.skip(ringing, NOW)
    assert outcome == "dismissed" and not t3.pending and t3.times_done == 0


def test_skip_one_shot(make_task):
    with pytest.raises(EngineError):
        engine.skip(make_task(next_due=NOW + HOUR), NOW)
    ringing, _ = engine.process(make_task(next_due=NOW), NOW)
    t2, outcome = engine.skip(ringing, NOW)
    assert outcome == "dismissed" and t2.state == DONE


def test_pause_resume_catches_up(make_task):
    t = make_task(interval_seconds=HOUR, next_due=NOW + 60)
    p = engine.pause(t)
    assert p.state == PAUSED
    with pytest.raises(EngineError):
        engine.pause(p)
    r = engine.resume(p, NOW + 5 * HOUR)
    assert r.state == ACTIVE and r.next_due > NOW + 5 * HOUR
    with pytest.raises(EngineError):
        engine.resume(r, NOW)


def test_resume_restarts_nag_if_ringing(make_task):
    t = make_task(interval_seconds=DAY, next_due=NOW, nag_seconds=5 * MINUTE)
    t, _ = engine.process(t, NOW)
    p = engine.pause(t)
    assert p.followup_at is None and p.pending
    r = engine.resume(p, NOW + HOUR)
    assert r.followup_at == NOW + HOUR + 5 * MINUTE


def test_reschedule_revives_finished_one_shot(make_task):
    done, _ = engine.complete(make_task(next_due=NOW + 60), NOW)
    revived = engine.reschedule(done, Schedule(), NOW, when=NOW + DAY)
    assert revived.state == ACTIVE and revived.next_due == NOW + DAY


def test_reschedule_keeps_time_if_no_when(make_task):
    t = make_task(interval_seconds=DAY, next_due=local(2026, 10, 22, 9))
    t2 = engine.reschedule(t, Schedule(weekdays=(0,)), NOW)
    nxt = as_local(t2.next_due)
    assert (nxt.weekday(), nxt.hour) == (0, 9)


def test_reschedule_one_shot_without_when_needs_when(make_task):
    done, _ = engine.complete(make_task(next_due=NOW + 60), NOW)
    with pytest.raises(EngineError):
        engine.reschedule(done, Schedule(), NOW)


def test_set_nag(make_task):
    t = make_task(interval_seconds=DAY, next_due=NOW)
    t, _ = engine.process(t, NOW)
    on = engine.set_nag(t, 600, NOW + 5)
    assert on.followup_at == NOW + 605 and on.followup_kind == "nag"
    off = engine.set_nag(on, None, NOW + 10)
    assert off.followup_at is None and off.nag_seconds is None
    snoozed = engine.snooze(t, NOW, 900)
    still = engine.set_nag(snoozed, 600, NOW)
    assert still.followup_kind == "snooze"  # changing nag doesn't cancel a snooze

#endregion
##xchronusx
