##xchronusx
"""
carzty.core.engine - the brains. decides when to yell at you and what happens when you push buttons.

Synopsis:
    task, fired = engine.process(task, now, max_nags=24)
    task, outcome = engine.complete(task, now)
    task = engine.snooze(task, now, 900)

Description:
    Pure functions. Task goes in, new Task comes out, nothing touches discord or
    the database in here. The scheduler and the slash commands call these and
    then save whatever comes back. That's the whole trick, and it's why the tests
    can fake time without monkeypatching the universe.

    Recurring schedules:
      * plain intervals under a day are just "+N seconds", no drama
      * whole-day intervals (1d, 2d, 1w) step in local wall-clock time, so 9am
        stays 9am when daylight saving does its stupid little dance
      * weekday sets (weekdays, mon/wed/fri) step a day at a time until they land
        on an allowed day, same local time

    If the bot was offline and missed a bunch of reminders, you get ONE reminder
    (flagged as late) and then it picks back up on the schedule. Nobody wants 37
    "drink water" pings at once.

Notes:
    Author: Zachary Wright (xchronusx)
    EngineError messages go straight to the user. keep 'em readable.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from carzty.core.models import ACTIVE, DONE, PAUSED, Task
from carzty.core.timeparse import DAY, DEFAULT_TIME, Schedule


class EngineError(ValueError):
    """Somebody asked for something that doesn't make sense right now."""


@dataclass(frozen=True)
class Fired:
    """A reminder that needs to go out."""

    kind: str  # "scheduled" | "nag" | "snooze"
    late_by: int  # seconds behind schedule (bot was asleep, etc)
    missed_previous: bool  # last reminder never got a Done
    nag_number: int  # 0 for the scheduled one, 1.. for nags
    gave_up: bool  # this is the last nag, we're done begging


#region OCCURRENCE MATH

def _add_wall_days(ts: int, days: int, tz: ZoneInfo) -> int:
    # aware datetime + timedelta is wall-clock math in python, which is exactly what we want here
    local = datetime.fromtimestamp(ts, tz)
    return int((local + timedelta(days=days)).timestamp())


def align_to_weekdays(ts: int, weekdays: tuple[int, ...] | None, tz: ZoneInfo) -> int:
    """Roll ts forward (same local time) until it lands on an allowed weekday."""
    if not weekdays:
        return ts
    local = datetime.fromtimestamp(ts, tz)
    for i in range(8):
        cand = local + timedelta(days=i)
        if cand.weekday() in weekdays:
            return int(cand.timestamp())
    return ts  # unreachable unless weekdays is garbage


def step(task: Task, ts: int) -> int:
    """The occurrence right after `ts`. Assumes the task is recurring."""
    tz = task.zone
    if task.weekdays:
        return align_to_weekdays(_add_wall_days(ts, 1, tz), task.weekdays, tz)
    interval = task.interval_seconds or 0
    if interval <= 0:
        raise EngineError("That task doesn't repeat.")
    if interval % DAY == 0:
        return _add_wall_days(ts, interval // DAY, tz)
    return ts + interval


def next_after(task: Task, due: int, now: int) -> int:
    """First occurrence strictly after `now`, walking forward from `due`."""
    if due > now:
        return due
    tz = task.zone

    if task.weekdays:
        behind_days = (now - due) // DAY
        if behind_days > 7:
            due = _add_wall_days(due, (behind_days // 7 - 1) * 7, tz)  # jump in whole weeks so the weekday holds
        while due <= now:
            due = step(task, due)
        return due

    interval = task.interval_seconds or 0
    if interval <= 0:
        raise EngineError("That task doesn't repeat.")

    if interval % DAY == 0:
        behind = (now - due) // interval
        if behind > 1:
            due = _add_wall_days(due, (behind - 1) * (interval // DAY), tz)
        while due <= now:
            due = step(task, due)
        return due

    return due + ((now - due) // interval + 1) * interval


def first_due(schedule: Schedule, tz: ZoneInfo, now: int, when: int | None = None) -> int:
    """Pick the first reminder time for a brand new (or rescheduled) task."""
    if when is not None:
        return align_to_weekdays(when, schedule.weekdays, tz)
    if schedule.once:
        raise EngineError("One-time reminders need a `when`. Like `in 20m`, `5pm` or `tomorrow 9am`.")
    if schedule.weekdays:
        local_now = datetime.fromtimestamp(now, tz)
        ts = int(datetime.combine(local_now.date(), DEFAULT_TIME, tzinfo=tz).timestamp())
        ts = align_to_weekdays(ts, schedule.weekdays, tz)
        while ts <= now:
            ts = align_to_weekdays(_add_wall_days(ts, 1, tz), schedule.weekdays, tz)
        return ts
    return now + int(schedule.interval_seconds or 0)

#endregion


#region THE TICK

def process(task: Task, now: int, max_nags: int = 24) -> tuple[Task, Fired | None]:
    """Called by the scheduler every tick. Returns the updated task and a Fired if something should go out."""
    if task.state != ACTIVE:
        return task, None

    scheduled_due = task.next_due is not None and task.next_due <= now
    followup_due = task.followup_at is not None and task.followup_at <= now

    if scheduled_due:
        late_by = now - int(task.next_due)
        missed = task.pending
        nxt = next_after(task, int(task.next_due), now) if task.recurring else None
        followup = now + task.nag_seconds if task.nag_seconds and max_nags > 0 else None
        updated = replace(
            task,
            next_due=nxt,
            pending=True,
            followup_at=followup,
            followup_kind="nag" if followup else None,
            nag_count=0,
            last_fired_at=now,
            times_fired=task.times_fired + 1,
            streak=0 if missed else task.streak,
        )
        return updated, Fired("scheduled", late_by, missed, 0, False)

    if followup_due:
        kind = task.followup_kind or "nag"
        late_by = now - int(task.followup_at)
        nag_count = task.nag_count + (1 if kind == "nag" else 0)
        followup = None
        if task.nag_seconds and nag_count < max_nags:
            followup = now + task.nag_seconds
        gave_up = kind == "nag" and followup is None
        updated = replace(
            task,
            pending=True,
            followup_at=followup,
            followup_kind="nag" if followup else None,
            nag_count=nag_count,
            last_fired_at=now,
        )
        return updated, Fired(kind, late_by, False, nag_count, gave_up)

    return task, None

#endregion


#region USER ACTIONS

def complete(task: Task, now: int) -> tuple[Task, str]:
    """
    Done button / `/task done`.

    outcome:
      "acked"    - it was ringing, now it's not, recurring task carries on
      "early"    - recurring task wasn't ringing, so this counts for the next one (which gets skipped)
      "finished" - one-shot is done done
    """
    if task.state == DONE:
        raise EngineError("That one's already done. Overachiever.")

    stats = dict(last_done_at=now, times_done=task.times_done + 1, streak=task.streak + 1)
    quiet = dict(pending=False, followup_at=None, followup_kind=None, nag_count=0)

    if not task.recurring:
        return replace(task, state=DONE, next_due=None, **quiet, **stats), "finished"

    if task.pending:
        return replace(task, **quiet, **stats), "acked"

    base = task.next_due if task.next_due is not None else now
    nxt = step(task, base) if base > now else next_after(task, step(task, base), now)
    return replace(task, next_due=nxt, **quiet, **stats), "early"


def snooze(task: Task, now: int, seconds: int) -> Task:
    """Snooze the reminder that's currently going off."""
    if task.state == PAUSED:
        raise EngineError("It's paused. Resume it first, then you can snooze it like a normal person.")
    if task.state == DONE or not task.pending:
        raise EngineError(
            "Nothing's going off right now, so there's nothing to snooze. "
            "Want to move it? Use `/task edit` with a new `when`, or `/task skip`."
        )
    if seconds <= 0:
        raise EngineError("Snooze for zero seconds? That's just... not snoozing.")
    return replace(task, followup_at=now + seconds, followup_kind="snooze")


def skip(task: Task, now: int) -> tuple[Task, str]:
    """
    Skip button / `/task skip`.

    outcome:
      "dismissed" - it was ringing, now it isn't, no credit given
      "skipped"   - the upcoming occurrence got skipped
    """
    if task.state == DONE:
        raise EngineError("It's already done. There's nothing left to skip.")

    quiet = dict(pending=False, followup_at=None, followup_kind=None, nag_count=0)

    if task.pending:
        if not task.recurring:
            return replace(task, state=DONE, next_due=None, **quiet), "dismissed"
        return replace(task, **quiet), "dismissed"

    if not task.recurring:
        raise EngineError("It's a one-time reminder, there's nothing to skip. Remove it or change the `when`.")

    base = task.next_due if task.next_due is not None else now
    nxt = step(task, base) if base > now else next_after(task, step(task, base), now)
    return replace(task, next_due=nxt), "skipped"


def pause(task: Task) -> Task:
    if task.state == DONE:
        raise EngineError("It's done. Can't pause a finished thing.")
    if task.state == PAUSED:
        raise EngineError("Already paused. It's not going anywhere.")
    return replace(task, state=PAUSED, followup_at=None, followup_kind=None)


def resume(task: Task, now: int) -> Task:
    if task.state != PAUSED:
        raise EngineError("It's not paused.")
    nxt = task.next_due
    if task.recurring and nxt is not None and nxt <= now:
        nxt = next_after(task, nxt, now)
    followup = now + task.nag_seconds if task.pending and task.nag_seconds else None
    return replace(
        task,
        state=ACTIVE,
        next_due=nxt,
        followup_at=followup,
        followup_kind="nag" if followup else None,
    )


def reschedule(task: Task, schedule: Schedule, now: int, when: int | None = None) -> Task:
    """
    `/task edit` with a new `every` and/or `when`.

    No `when` + a future next_due = keep the time you had (just snapped to the new weekdays).
    No `when` + nothing scheduled = start fresh from now.
    Rescheduling a finished one-shot brings it back from the dead.
    """
    tz = task.zone
    if when is None and task.next_due is not None and task.next_due > now:
        nxt = align_to_weekdays(task.next_due, schedule.weekdays, tz)
    else:
        nxt = first_due(schedule, tz, now, when)

    return replace(
        task,
        interval_seconds=schedule.interval_seconds,
        weekdays=schedule.weekdays,
        next_due=nxt,
        state=PAUSED if task.state == PAUSED else ACTIVE,
        pending=False,
        followup_at=None,
        followup_kind=None,
        nag_count=0,
    )


def set_nag(task: Task, nag_seconds: int | None, now: int) -> Task:
    """Turn nagging on/off. If it's ringing right now, the new nag kicks in from now."""
    followup = task.followup_at
    kind = task.followup_kind
    if task.followup_kind != "snooze":
        followup = now + nag_seconds if (task.pending and nag_seconds and task.state == ACTIVE) else None
        kind = "nag" if followup else None
    return replace(task, nag_seconds=nag_seconds, followup_at=followup, followup_kind=kind)

#endregion


def utcnow() -> int:
    return int(datetime.now(timezone.utc).timestamp())
##xchronusx
