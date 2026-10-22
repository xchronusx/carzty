##xchronusx
"""
carzty.core.timeparse - turns whatever you typed into actual times.

Synopsis:
    parse_duration("1h30m")            -> 5400
    parse_every("mon,wed,fri")         -> Schedule(weekdays=(0, 2, 4))
    parse_when("tomorrow 9am", tz, now) -> aware datetime in your timezone

Description:
    Discord gives us a text box, humans type garbage into it. This module is the
    bouncer. No discord imports in here on purpose, so it can be tested without
    a bot token or an internet connection or a will to live.

    Durations:  30s, 15m, 2h, 1d, 1w, 1h30m, "2 hours", "an hour", hourly,
                daily, weekly, fortnightly, "every other day"
    Schedules:  any duration, weekdays, weekends, mon,wed,fri, mon-fri, tue/thu,
                once (or nothing) for a one-shot
    Times:      now, in 20m, 20m, 9am, 9:30pm, 21:00, noon, midnight, morning,
                afternoon, evening, tonight, today 5pm, tomorrow 8am, friday 3pm,
                next monday, 2026-10-25 14:00, 10/25 2pm, oct 25 6pm, 25 oct

Notes:
    Author: Zachary Wright (xchronusx)
    Dates are US style (month/day) when you use slashes. ISO (yyyy-mm-dd) always
    works if you're one of those people.
    A bare number like "9" gets rejected. 9 what. am? pm? be a grown up.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


class ParseError(ValueError):
    """Raised when the input is nonsense. The message is shown to the user, so keep it human."""


#region UNITS

MINUTE = 60
HOUR = 60 * MINUTE
DAY = 24 * HOUR
WEEK = 7 * DAY

_UNIT_SECONDS = {
    "s": 1, "sec": 1, "secs": 1, "second": 1, "seconds": 1,
    "m": MINUTE, "min": MINUTE, "mins": MINUTE, "minute": MINUTE, "minutes": MINUTE,
    "h": HOUR, "hr": HOUR, "hrs": HOUR, "hour": HOUR, "hours": HOUR,
    "d": DAY, "day": DAY, "days": DAY,
    "w": WEEK, "wk": WEEK, "wks": WEEK, "week": WEEK, "weeks": WEEK,
}

# words people use instead of numbers, because of course they do
_DURATION_ALIASES = {
    "hourly": HOUR,
    "daily": DAY,
    "nightly": DAY,
    "weekly": WEEK,
    "fortnightly": 2 * WEEK,
    "biweekly": 2 * WEEK,
    "other day": 2 * DAY,
    "other week": 2 * WEEK,
}

_DURATION_PART = re.compile(
    r"(?P<num>\d+(?:\.\d+)?|an?)\s*(?P<unit>[a-z]+)"
)

#endregion

#region WEEKDAYS

_WEEKDAY_NAMES = {
    "mon": 0, "monday": 0, "mondays": 0,
    "tue": 1, "tues": 1, "tuesday": 1, "tuesdays": 1,
    "wed": 2, "weds": 2, "wednesday": 2, "wednesdays": 2,
    "thu": 3, "thur": 3, "thurs": 3, "thursday": 3, "thursdays": 3,
    "fri": 4, "friday": 4, "fridays": 4,
    "sat": 5, "saturday": 5, "saturdays": 5,
    "sun": 6, "sunday": 6, "sundays": 6,
}

WEEKDAY_SHORT = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}

#endregion


def _clean(text: str) -> str:
    s = (text or "").strip().lower()
    s = s.replace(",", " ").replace("&", " ")
    s = re.sub(r"\s+", " ", s)
    return s.strip(" .")


#region DURATIONS

def parse_duration(text: str) -> int:
    """'1h30m' -> 5400. Raises ParseError if it can't make sense of it."""
    s = _clean(text)
    s = re.sub(r"^(every|in)\s+", "", s)
    s = re.sub(r"\band\b", " ", s).strip()
    s = re.sub(r"\s+", " ", s)

    if not s:
        raise ParseError("Gonna need an actual duration there. Try `30m`, `2h` or `1d`.")

    if s in _DURATION_ALIASES:
        return _DURATION_ALIASES[s]

    # "hour", "day", "week" on their own (like "every hour")
    if s in _UNIT_SECONDS and len(s) > 1:
        return _UNIT_SECONDS[s]

    total = 0.0
    pos = 0
    squashed = s.replace(" ", "")
    for match in _DURATION_PART.finditer(squashed):
        if match.start() != pos:
            break
        num_txt, unit = match.group("num"), match.group("unit")
        if unit not in _UNIT_SECONDS:
            raise ParseError(f"`{unit}` isn't a unit I know. Use s, m, h, d or w.")
        num = 1.0 if num_txt in ("a", "an") else float(num_txt)
        total += num * _UNIT_SECONDS[unit]
        pos = match.end()

    if pos != len(squashed) or pos == 0:
        raise ParseError(
            f"`{text.strip()}` isn't a duration I understand. Try `30m`, `2h`, `1h30m`, `1d` or `1w`."
        )

    seconds = int(round(total))
    if seconds <= 0:
        raise ParseError("Zero seconds? Bold. No.")
    return seconds


def format_duration(seconds: int) -> str:
    """5400 -> '1h 30m'. Biggest units first, skips the zeros."""
    seconds = int(seconds)
    if seconds <= 0:
        return "0s"
    parts = []
    for label, size in (("w", WEEK), ("d", DAY), ("h", HOUR), ("m", MINUTE), ("s", 1)):
        if seconds >= size:
            qty, seconds = divmod(seconds, size)
            parts.append(f"{qty}{label}")
    return " ".join(parts)

#endregion


#region SCHEDULES

@dataclass(frozen=True)
class Schedule:
    """How often a task repeats. Both None means it's a one-shot."""

    interval_seconds: int | None = None
    weekdays: tuple[int, ...] | None = None

    @property
    def once(self) -> bool:
        return self.interval_seconds is None and not self.weekdays


ONCE = Schedule()


def _parse_weekday_list(s: str) -> tuple[int, ...] | None:
    """'mon,wed,fri' / 'mon-fri' / 'tue/thu' / 'monday and thursday' -> sorted tuple. None if it isn't one."""
    s = s.replace("/", " ").replace("+", " ")
    s = re.sub(r"\band\b", " ", s)
    s = re.sub(r"\s*-\s*", "-", s)
    tokens = [t for t in s.split(" ") if t]
    if not tokens:
        return None

    days: set[int] = set()
    for tok in tokens:
        if "-" in tok:
            start, _, end = tok.partition("-")
            if start not in _WEEKDAY_NAMES or end not in _WEEKDAY_NAMES:
                return None
            a, b = _WEEKDAY_NAMES[start], _WEEKDAY_NAMES[end]
            i = a
            while True:
                days.add(i)
                if i == b:
                    break
                i = (i + 1) % 7
        elif tok in _WEEKDAY_NAMES:
            days.add(_WEEKDAY_NAMES[tok])
        else:
            return None
    return tuple(sorted(days))


def parse_every(text: str | None) -> Schedule:
    """Parse the `every` field. Blank / once / never -> ONCE."""
    s = _clean(text or "")
    s = re.sub(r"^every\s+", "", s)

    if s in ("", "once", "one time", "onetime", "never", "none", "no", "off", "single"):
        return ONCE
    if s in ("weekday", "weekdays", "workday", "workdays", "work days"):
        return Schedule(weekdays=(0, 1, 2, 3, 4))
    if s in ("weekend", "weekends"):
        return Schedule(weekdays=(5, 6))
    if s in ("day", "daily", "every day", "everyday"):
        return Schedule(interval_seconds=DAY)

    days = _parse_weekday_list(s)
    if days is not None:
        if len(days) == 7:
            return Schedule(interval_seconds=DAY)  # every single day is just... daily
        return Schedule(weekdays=days)

    return Schedule(interval_seconds=parse_duration(s))


def describe_schedule(interval_seconds: int | None, weekdays: tuple[int, ...] | None) -> str:
    """Human version of a schedule for embeds. 'every 2h', 'weekdays', 'Mon, Wed & Fri'."""
    if weekdays:
        wd = tuple(sorted(weekdays))
        if wd == (0, 1, 2, 3, 4):
            return "weekdays"
        if wd == (5, 6):
            return "weekends"
        names = [WEEKDAY_SHORT[d] for d in wd]
        if len(names) == 1:
            return f"every {names[0]}"
        return ", ".join(names[:-1]) + f" & {names[-1]}"
    if interval_seconds:
        friendly = {
            MINUTE: "every minute",
            HOUR: "every hour",
            DAY: "every day",
            WEEK: "every week",
            2 * DAY: "every other day",
            2 * WEEK: "every other week",
        }
        return friendly.get(interval_seconds, f"every {format_duration(interval_seconds)}")
    return "once"

#endregion


#region WHEN

DEFAULT_TIME = time(9, 0)  # when somebody says "tomorrow" and nothing else. 9am, like a civilized person.

_NAMED_TIMES = {
    "noon": time(12, 0),
    "midday": time(12, 0),
    "midnight": time(0, 0),
    "morning": time(9, 0),
    "afternoon": time(15, 0),
    "evening": time(18, 0),
    "tonight": time(20, 0),
    "night": time(20, 0),
    "eod": time(17, 0),
}

_TIME_12H = re.compile(r"(?:^|\s)(?P<h>\d{1,2})(?:[:.](?P<m>\d{2}))?\s*(?P<ap>am|pm|a|p)(?=\s|$)")
_TIME_24H = re.compile(r"(?:^|\s)(?P<h>\d{1,2}):(?P<m>\d{2})(?=\s|$)")
_NAMED_TIME_RE = re.compile(r"(?:^|\s)(?P<w>" + "|".join(_NAMED_TIMES) + r")(?=\s|$)")

_ISO_DATE = re.compile(r"^(?P<y>\d{4})-(?P<mo>\d{1,2})-(?P<d>\d{1,2})$")
_US_DATE = re.compile(r"^(?P<mo>\d{1,2})/(?P<d>\d{1,2})(?:/(?P<y>\d{2}|\d{4}))?$")
_MONTH_FIRST = re.compile(r"^(?P<mon>[a-z]+)\s+(?P<d>\d{1,2})(?:st|nd|rd|th)?(?:\s+(?P<y>\d{4}))?$")
_DAY_FIRST = re.compile(r"^(?P<d>\d{1,2})(?:st|nd|rd|th)?\s+(?P<mon>[a-z]+)(?:\s+(?P<y>\d{4}))?$")


def _extract_time(s: str) -> tuple[time | None, str]:
    """Pull the time-of-day out of the string. Returns (time or None, leftover text)."""
    m = _TIME_12H.search(s)
    if m:
        hour, minute = int(m.group("h")), int(m.group("m") or 0)
        if not 1 <= hour <= 12 or minute > 59:
            raise ParseError(f"`{m.group(0).strip()}` isn't a real time.")
        hour = hour % 12 + (12 if m.group("ap").startswith("p") else 0)
        return time(hour, minute), (s[: m.start()] + " " + s[m.end():]).strip()

    m = _TIME_24H.search(s)
    if m:
        hour, minute = int(m.group("h")), int(m.group("m"))
        if hour > 23 or minute > 59:
            raise ParseError(f"`{m.group(0).strip()}` isn't a real time.")
        return time(hour, minute), (s[: m.start()] + " " + s[m.end():]).strip()

    m = _NAMED_TIME_RE.search(s)
    if m:
        return _NAMED_TIMES[m.group("w")], (s[: m.start()] + " " + s[m.end():]).strip()

    return None, s


def _build_date(year: int | None, month: int, day: int, today: date) -> date:
    try:
        if year is not None:
            return date(year, month, day)
        candidate = date(today.year, month, day)
        if candidate < today:
            candidate = date(today.year + 1, month, day)
        return candidate
    except ValueError:
        raise ParseError(f"{month}/{day} isn't a real date. Calendars, man.") from None


def _extract_date(s: str, today: date) -> tuple[date | None, bool]:
    """Returns (date or None, rolls_weekly). rolls_weekly means it was a weekday name like 'friday'."""
    s = re.sub(r"^(on|this)\s+", "", s).strip()
    if not s:
        return None, False

    if s in ("today", "tod", "tdy"):
        return today, False
    if s in ("tomorrow", "tmrw", "tmr", "tomorow", "tommorow", "tommorrow"):
        return today + timedelta(days=1), False

    is_next = False
    if s.startswith("next "):
        is_next = True
        s = s[5:].strip()

    if s in _WEEKDAY_NAMES:
        target = _WEEKDAY_NAMES[s]
        delta = (target - today.weekday()) % 7
        if is_next and delta == 0:
            delta = 7
        return today + timedelta(days=delta), not is_next

    if is_next and s == "week":
        return today + timedelta(days=7), False

    m = _ISO_DATE.match(s)
    if m:
        return _build_date(int(m.group("y")), int(m.group("mo")), int(m.group("d")), today), False

    m = _US_DATE.match(s)
    if m:
        year = m.group("y")
        if year is not None:
            year = int(year) + (2000 if len(year) == 2 else 0)
        return _build_date(year, int(m.group("mo")), int(m.group("d")), today), False

    for rx in (_MONTH_FIRST, _DAY_FIRST):
        m = rx.match(s)
        if m and m.group("mon") in _MONTHS:
            year = int(m.group("y")) if m.group("y") else None
            return _build_date(year, _MONTHS[m.group("mon")], int(m.group("d")), today), False

    raise ParseError(
        f"No clue what day `{s}` is. Try `tomorrow`, `friday`, `2026-10-25`, `10/25` or `oct 25`."
    )


def _relative(now: datetime, seconds: int, tz: ZoneInfo) -> datetime:
    return (now.astimezone(timezone.utc) + timedelta(seconds=seconds)).astimezone(tz)


def parse_when(text: str, tz: ZoneInfo, now: datetime) -> datetime:
    """
    Parse a 'when' into an aware datetime in `tz`.

    `now` must be timezone aware. Times that already passed today roll to tomorrow,
    dates without a year roll to next year, explicit past dates get yelled at.
    """
    if now.tzinfo is None:
        raise ValueError("now must be timezone aware")  # this one's for me, not the user

    local_now = now.astimezone(tz)
    s = _clean(text)
    s = re.sub(r"(?<=\d)t(?=\d)", " ", s)  # ISO 2026-10-25T14:00
    s = re.sub(r"^at\s+", "", s)

    if not s:
        raise ParseError("When though? Try `9am`, `in 20m`, `tomorrow 8am` or `friday 3pm`.")

    if s in ("now", "asap", "rn", "right now"):
        return local_now

    # relative: "in 20m" or just "20m". done in UTC so DST can't eat an hour of your snooze
    if s.startswith("in "):
        return _relative(now, parse_duration(s[3:]), tz)
    if re.match(r"^(\d+(\.\d+)?|an?)\s*[a-z]", s) and not re.search(r"\d\s*(am|pm|a|p)$", s):
        try:
            return _relative(now, parse_duration(s), tz)
        except ParseError:
            pass  # might be "25 oct" or whatever, keep going

    if re.fullmatch(r"\d{1,2}", s):
        raise ParseError(f"`{s}` what? am or pm? Say `{s}am`, `{s}pm`, or use 24h like `{int(s):02d}:00`.")

    tod, rest = _extract_time(s)
    rest = re.sub(r"\s+at$|^at\s+|\bat\b", " ", rest).strip()
    rest = re.sub(r"\s+", " ", rest)
    day, rolls_weekly = _extract_date(rest, local_now.date())

    if day is None and tod is None:
        raise ParseError(f"`{text.strip()}` doesn't look like a time to me.")

    if day is None:
        # time only: today if it's still ahead of us, else tomorrow
        candidate = datetime.combine(local_now.date(), tod, tzinfo=tz)
        if candidate <= local_now:
            candidate = datetime.combine(local_now.date() + timedelta(days=1), tod, tzinfo=tz)
        return candidate

    candidate = datetime.combine(day, tod or DEFAULT_TIME, tzinfo=tz)
    if candidate <= local_now:
        if rolls_weekly:
            # "friday 9am" said on friday at 10am means next friday
            return candidate + timedelta(days=7)
        raise ParseError(f"<t:{int(candidate.timestamp())}:f> already happened. I can't remind you in the past.")
    return candidate

#endregion
##xchronusx
