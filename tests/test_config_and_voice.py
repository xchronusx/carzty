##xchronusx
"""
tests/test_config_and_voice.py - .env parsing and making sure no tone is missing a line.

Notes:
    Author: Zachary Wright (xchronusx)
"""

from __future__ import annotations

import random

import pytest

from carzty.config import ConfigError, load_config
from carzty.voice import LINES, nag_key, say

#region CONFIG


def test_defaults():
    cfg = load_config({"DISCORD_TOKEN": "abc"})
    assert cfg.default_tz == "UTC" and cfg.default_tone == "salty"
    assert cfg.snooze_options == (900, 3600)
    assert cfg.min_interval == 60 and cfg.max_nags == 24


def test_full_env():
    cfg = load_config(
        {
            "DISCORD_TOKEN": "abc",
            "DEFAULT_TIMEZONE": "America/Phoenix",
            "DEFAULT_TONE": "UNHINGED",
            "ALLOWED_USER_IDS": "123, 456",
            "MIN_INTERVAL": "5m",
            "SNOOZE_OPTIONS": "10m,30m,2h",
            "TICK_SECONDS": "2.5",
            "DATABASE_PATH": "elsewhere/x.db",
        }
    )
    assert cfg.default_tone == "unhinged"
    assert cfg.allowed_user_ids == frozenset({123, 456})
    assert cfg.min_interval == 300
    assert cfg.snooze_options == (600, 1800, 7200)
    assert cfg.tick_seconds == 2.5
    assert cfg.database_path.parts[-2:] == ("elsewhere", "x.db")


@pytest.mark.parametrize(
    "env",
    [
        {},
        {"DISCORD_TOKEN": "paste-your-token-here"},
        {"DISCORD_TOKEN": "x", "DEFAULT_TIMEZONE": "Mars/Olympus_Mons"},
        {"DISCORD_TOKEN": "x", "DEFAULT_TONE": "polite"},
        {"DISCORD_TOKEN": "x", "ALLOWED_USER_IDS": "bob"},
        {"DISCORD_TOKEN": "x", "MAX_TASKS_PER_USER": "0"},
        {"DISCORD_TOKEN": "x", "MIN_INTERVAL": "soon"},
        {"DISCORD_TOKEN": "x", "SNOOZE_OPTIONS": "1m,2m,3m,4m"},
        {"DISCORD_TOKEN": "x", "TICK_SECONDS": "0.1"},
        {"DISCORD_TOKEN": "x", "LOG_LEVEL": "LOUD"},
    ],
)
def test_bad_config_is_loud(env):
    with pytest.raises(ConfigError):
        load_config(env)


def test_check_mode_doesnt_need_token():
    assert load_config({}, require_token=False).token == ""

#endregion


#region VOICE

KEYS = set(LINES["salty"])


@pytest.mark.parametrize("tone", list(LINES))
def test_every_tone_has_every_key(tone):
    assert set(LINES[tone]) == KEYS
    for key, options in LINES[tone].items():
        assert options, f"{tone}.{key} is empty"


@pytest.mark.parametrize("tone", list(LINES))
def test_every_line_formats(tone):
    fmt = dict(title="t", nag=3, streak=4, until="<t:1:t>", due="<t:1:R>")
    for options in LINES[tone].values():
        for line in options:
            line.format(**fmt)  # blows up if somebody typo'd a placeholder


def test_nag_escalates():
    assert [nag_key(n) for n in (1, 2, 3, 5, 6, 11, 12, 99)] == [
        "nag_1", "nag_1", "nag_2", "nag_2", "nag_3", "nag_3", "nag_4", "nag_4",
    ]


class _First(random.Random):
    def choice(self, seq):
        return seq[0]


def test_say_fills_placeholders_and_falls_back():
    assert say("salty", "nag", rng=_First(), nag=7) == "Nag #7. I'm not mad. I'm just disappointed."
    assert say("chill", "done_streak", rng=_First(), streak=4) == "Nice work, that's 4 in a row."
    assert say("nonsense-tone", "done")  # unknown tone falls back to salty
    assert say("salty", "no-such-key") == ""

#endregion
##xchronusx
