##xchronusx
"""
carzty.config - reads .env so you don't have to hardcode a token like an animal.

Synopsis:
    cfg = load_config()          # reads os.environ (python -m carzty loads .env first)

Description:
    Every knob lives in .env. See .env.example for the full list with comments.
    Anything missing gets a sane default, anything malformed gets a loud error at
    startup instead of a weird bug at 3am.

Notes:
    Author: Zachary Wright (xchronusx)
    Relative paths are relative to CARZTY_HOME, not wherever you happened to be
    standing when you ran it. CARZTY_HOME is:
      * whatever you set CARZTY_HOME to, if you set it
      * the repo folder, if you're running from a checkout (the normal way)
      * otherwise a per-user app folder (pip/pipx installs):
          Windows  %LOCALAPPDATA%/Carzty
          macOS    ~/Library/Application Support/Carzty
          Linux    ~/.local/share/carzty
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from carzty.core.timeparse import ParseError, parse_duration

ROOT = Path(__file__).resolve().parents[1]  # where the code lives

TONES = ("chill", "salty", "unhinged")


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Config:
    token: str
    default_tz: str = "UTC"
    default_tone: str = "salty"
    database_path: Path = ROOT / "data" / "carzty.db"
    log_dir: Path = ROOT / "logs"
    log_level: str = "INFO"
    allowed_user_ids: frozenset[int] = field(default_factory=frozenset)
    max_tasks_per_user: int = 50
    min_interval: int = 60
    max_nags: int = 24
    tick_seconds: float = 10.0
    snooze_options: tuple[int, ...] = (15 * 60, 60 * 60)
    purge_done_after_days: int = 30


def app_home(env: Mapping[str, str] | None = None) -> Path:
    """Where .env, data/ and logs/ live. See the notes up top."""
    env = os.environ if env is None else env
    custom = (env.get("CARZTY_HOME") or "").strip()
    if custom:
        return Path(custom).expanduser().resolve()
    if (ROOT / "pyproject.toml").is_file():
        return ROOT  # running from a checkout. keep everything next to the code
    if sys.platform == "win32":
        return Path(env.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")) / "Carzty"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Carzty"
    return Path(env.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share")) / "carzty"


def _path(value: str | None, default: Path, home: Path) -> Path:
    if not value:
        return default
    p = Path(value).expanduser()
    return p if p.is_absolute() else (home / p)


def _int(env: Mapping[str, str], key: str, default: int, minimum: int = 0) -> int:
    raw = (env.get(key) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ConfigError(f"{key} has to be a whole number, got {raw!r}") from None
    if value < minimum:
        raise ConfigError(f"{key} has to be at least {minimum}, got {value}")
    return value


def _duration(env: Mapping[str, str], key: str, default: int) -> int:
    raw = (env.get(key) or "").strip()
    if not raw:
        return default
    try:
        return parse_duration(raw)
    except ParseError as exc:
        raise ConfigError(f"{key}: {exc}") from None


def load_config(env: Mapping[str, str] | None = None, require_token: bool = True) -> Config:
    env = os.environ if env is None else env

    token = (env.get("DISCORD_TOKEN") or "").strip()
    if require_token and (not token or token.lower().startswith("paste")):
        raise ConfigError(
            "DISCORD_TOKEN is empty. Copy .env.example to .env and paste your bot token in. "
            "docs/discord-setup.md walks you through getting one."
        )

    default_tz = (env.get("DEFAULT_TIMEZONE") or "UTC").strip()
    try:
        ZoneInfo(default_tz)
    except (ZoneInfoNotFoundError, ValueError):
        raise ConfigError(
            f"DEFAULT_TIMEZONE {default_tz!r} isn't a real IANA timezone. Try something like America/Phoenix or Europe/London. "
            "(On Windows, make sure the tzdata package is installed: pip install tzdata)"
        ) from None

    tone = (env.get("DEFAULT_TONE") or "salty").strip().lower()
    if tone not in TONES:
        raise ConfigError(f"DEFAULT_TONE has to be one of {', '.join(TONES)}. got {tone!r}")

    allowed: set[int] = set()
    for chunk in (env.get("ALLOWED_USER_IDS") or "").replace(";", ",").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if not chunk.isdigit():
            raise ConfigError(f"ALLOWED_USER_IDS should be numeric Discord user IDs, got {chunk!r}")
        allowed.add(int(chunk))

    snooze: list[int] = []
    for chunk in (env.get("SNOOZE_OPTIONS") or "15m,1h").split(","):
        if chunk.strip():
            try:
                snooze.append(parse_duration(chunk))
            except ParseError as exc:
                raise ConfigError(f"SNOOZE_OPTIONS: {exc}") from None
    if not snooze:
        snooze = [15 * 60]
    if len(snooze) > 3:
        raise ConfigError("SNOOZE_OPTIONS: three snooze buttons max. Discord rows have limits and so do I.")

    tick_raw = (env.get("TICK_SECONDS") or "10").strip()
    try:
        tick = float(tick_raw)
    except ValueError:
        raise ConfigError(f"TICK_SECONDS has to be a number, got {tick_raw!r}") from None
    if tick < 1:
        raise ConfigError("TICK_SECONDS under 1 is just hammering sqlite for fun. 1 minimum.")

    log_level = (env.get("LOG_LEVEL") or "INFO").strip().upper()
    if log_level not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        raise ConfigError(f"LOG_LEVEL {log_level!r} isn't a log level")

    home = app_home(env)
    return Config(
        token=token,
        default_tz=default_tz,
        default_tone=tone,
        database_path=_path(env.get("DATABASE_PATH"), home / "data" / "carzty.db", home),
        log_dir=_path(env.get("LOG_DIR"), home / "logs", home),
        log_level=log_level,
        allowed_user_ids=frozenset(allowed),
        max_tasks_per_user=_int(env, "MAX_TASKS_PER_USER", 50, minimum=1),
        min_interval=_duration(env, "MIN_INTERVAL", 60),
        max_nags=_int(env, "MAX_NAGS", 24, minimum=1),
        tick_seconds=tick,
        snooze_options=tuple(snooze),
        purge_done_after_days=_int(env, "PURGE_DONE_AFTER_DAYS", 30, minimum=0),
    )
##xchronusx
