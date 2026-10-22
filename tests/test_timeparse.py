##xchronusx
"""
tests/test_timeparse.py - making sure "tomorrow 9am" means tomorrow at 9am. revolutionary stuff.

Notes:
    Author: Zachary Wright (xchronusx)
    now = Wed 2026-10-21 20:00 Phoenix
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from carzty.core.timeparse import (
    DAY,
    HOUR,
    MINUTE,
    WEEK,
    ParseError,
    Schedule,
    describe_schedule,
    format_duration,
    parse_duration,
    parse_every,
    parse_when,
)
from tests.conftest import NYC, PHX

#region DURATIONS


@pytest.mark.parametrize(
    ("text", "seconds"),
    [
        ("30s", 30),
        ("15m", 15 * MINUTE),
        ("15 min", 15 * MINUTE),
        ("2h", 2 * HOUR),
        ("2 hours", 2 * HOUR),
        ("1h30m", 90 * MINUTE),
        ("1h 30m", 90 * MINUTE),
        ("1 hour and 30 minutes", 90 * MINUTE),
        ("1.5h", 90 * MINUTE),
        ("an hour", HOUR),
        ("a day", DAY),
        ("1d", DAY),
        ("1w", WEEK),
        ("2 weeks", 2 * WEEK),
        ("every 2 hours", 2 * HOUR),
        ("in 20m", 20 * MINUTE),
        ("hourly", HOUR),
        ("daily", DAY),
        ("weekly", WEEK),
        ("fortnightly", 2 * WEEK),
        ("hour", HOUR),
        ("other day", 2 * DAY),
        ("  45M  ", 45 * MINUTE),
    ],
)
def test_parse_duration(text, seconds):
    assert parse_duration(text) == seconds


@pytest.mark.parametrize("text", ["", "15", "soon", "5 bananas", "0m", "m", "h1"])
def test_parse_duration_rejects_garbage(text):
    with pytest.raises(ParseError):
        parse_duration(text)


@pytest.mark.parametrize(
    ("seconds", "text"),
    [(30, "30s"), (90 * MINUTE, "1h 30m"), (DAY, "1d"), (WEEK + DAY, "1w 1d"), (0, "0s"), (3661, "1h 1m 1s")],
)
def test_format_duration(seconds, text):
    assert format_duration(seconds) == text

#endregion


#region SCHEDULES


@pytest.mark.parametrize("text", [None, "", "once", "never", "off", "none"])
def test_every_once(text):
    assert parse_every(text).once


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("30m", Schedule(interval_seconds=30 * MINUTE)),
        ("every 2h", Schedule(interval_seconds=2 * HOUR)),
        ("daily", Schedule(interval_seconds=DAY)),
        ("every day", Schedule(interval_seconds=DAY)),
        ("weekdays", Schedule(weekdays=(0, 1, 2, 3, 4))),
        ("weekends", Schedule(weekdays=(5, 6))),
        ("mon,wed,fri", Schedule(weekdays=(0, 2, 4))),
        ("mon, wed & fri", Schedule(weekdays=(0, 2, 4))),
        ("Monday and Thursday", Schedule(weekdays=(0, 3))),
        ("tue/thu", Schedule(weekdays=(1, 3))),
        ("mon-fri", Schedule(weekdays=(0, 1, 2, 3, 4))),
        ("fri-mon", Schedule(weekdays=(0, 4, 5, 6))),
        ("sundays", Schedule(weekdays=(6,))),
        ("mon-sun", Schedule(interval_seconds=DAY)),
    ],
)
def test_every(text, expected):
    assert parse_every(text) == expected


def test_every_rejects_garbage():
    with pytest.raises(ParseError):
        parse_every("whenever i feel like it")


@pytest.mark.parametrize(
    ("interval", "weekdays", "text"),
    [
        (HOUR, None, "every hour"),
        (2 * HOUR, None, "every 2h"),
        (DAY, None, "every day"),
        (2 * DAY, None, "every other day"),
        (None, (0, 1, 2, 3, 4), "weekdays"),
        (None, (5, 6), "weekends"),
        (None, (0, 2, 4), "Mon, Wed & Fri"),
        (None, (3,), "every Thu"),
        (None, None, "once"),
    ],
)
def test_describe_schedule(interval, weekdays, text):
    assert describe_schedule(interval, weekdays) == text

#endregion


#region WHEN


def _when(text, now_dt, tz=PHX):
    return parse_when(text, tz, now_dt)


def test_when_requires_aware_now():
    with pytest.raises(ValueError):
        parse_when("9am", PHX, datetime(2026, 1, 1))


def test_now(now_dt):
    assert _when("now", now_dt) == now_dt


@pytest.mark.parametrize(("text", "delta"), [("in 20m", 20 * MINUTE), ("20m", 20 * MINUTE), ("in an hour", HOUR), ("2h", 2 * HOUR)])
def test_relative(now_dt, text, delta):
    assert _when(text, now_dt) == now_dt + timedelta(seconds=delta)


def test_time_later_today(now_dt):
    got = _when("9:30pm", now_dt)
    assert (got.year, got.month, got.day, got.hour, got.minute) == (2026, 10, 21, 21, 30)


def test_time_already_passed_rolls_to_tomorrow(now_dt):
    got = _when("9am", now_dt)
    assert (got.month, got.day, got.hour) == (10, 22, 9)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("21:00", (10, 21, 21, 0)),
        ("noon", (10, 22, 12, 0)),
        ("midnight", (10, 22, 0, 0)),
        ("tonight", (10, 22, 20, 0)),  # it's 20:00 exactly, so "tonight" already happened. tomorrow then
        ("tomorrow", (10, 22, 9, 0)),
        ("tomorrow 8am", (10, 22, 8, 0)),
        ("tmrw at 5:15 pm", (10, 22, 17, 15)),
        ("at 9am tomorrow", (10, 22, 9, 0)),
        ("tomorrow morning", (10, 22, 9, 0)),
        ("friday 3pm", (10, 23, 15, 0)),
        ("fri", (10, 23, 9, 0)),
        ("monday at 9am", (10, 26, 9, 0)),
        ("wednesday 9pm", (10, 21, 21, 0)),  # today's wednesday and 9pm is still ahead
        ("wednesday 9am", (10, 28, 9, 0)),  # today's wednesday but 9am is gone, so next week
        ("next wednesday", (10, 28, 9, 0)),
        ("next week", (10, 28, 9, 0)),
        ("2026-10-25 14:00", (10, 25, 14, 0)),
        ("2026-10-25T14:00", (10, 25, 14, 0)),
        ("2026-12-01", (12, 1, 9, 0)),
        ("10/25 2pm", (10, 25, 14, 0)),
        ("10/25/26 2pm", (10, 25, 14, 0)),
        ("oct 25 6pm", (10, 25, 18, 0)),
        ("25 oct", (10, 25, 9, 0)),
        ("october 25th at 7:30am", (10, 25, 7, 30)),
        ("9.30pm", (10, 21, 21, 30)),
        ("1/5", (1, 5, 9, 0)),  # january already passed this year, so it's next year
    ],
)
def test_when_forms(now_dt, text, expected):
    got = _when(text, now_dt)
    assert (got.month, got.day, got.hour, got.minute) == expected


def test_date_without_year_rolls_to_next_year(now_dt):
    assert _when("1/5", now_dt).year == 2027


@pytest.mark.parametrize("text", ["today 8am", "2026-01-01 9am", "10/20/2026"])
def test_explicit_past_is_rejected(now_dt, text):
    with pytest.raises(ParseError):
        _when(text, now_dt)


@pytest.mark.parametrize("text", ["", "9", "13pm", "25:00", "2/30", "someday", "the heat death of the universe"])
def test_when_garbage(now_dt, text):
    with pytest.raises(ParseError):
        _when(text, now_dt)


def test_when_respects_timezone():
    # 03:00 UTC thursday is 23:00 wednesday in new york. "9am" there = 13:00 UTC thursday
    now = datetime(2026, 10, 22, 3, 0, tzinfo=timezone.utc)
    got = parse_when("9am", NYC, now)
    assert got.astimezone(timezone.utc) == datetime(2026, 10, 22, 13, 0, tzinfo=timezone.utc)


def test_relative_is_real_time_across_dst():
    # DST ends nov 1 2026 at 2am in new york. "in 2h" from 12:30am is still 2 real hours
    now = datetime(2026, 11, 1, 0, 30, tzinfo=NYC).astimezone(timezone.utc)
    got = parse_when("in 2h", NYC, now)
    assert (got.astimezone(timezone.utc) - now) == timedelta(hours=2)

#endregion
##xchronusx
