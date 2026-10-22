##xchronusx
"""
carzty.setup_wizard - `carzty setup`. a few questions, then your .env is done.

Synopsis:
    python -m carzty setup
    python -m carzty setup --token XXX --timezone America/Phoenix --tone salty --lock --yes

Description:
    The thing every installer runs, so nobody has to hand-edit a config file.
      1. bot token - hidden input, sanity checked, then checked with Discord for real
      2. timezone  - sniffed from your OS (registry on Windows, /etc/localtime elsewhere)
      3. tone      - chill / salty / unhinged
      4. lock      - Discord tells us who owns the bot, so we offer to lock it to just you
    Then it writes .env (keeping any other settings you already had) and prints
    the invite link, so you never have to dig through the developer portal for it.

    --yes takes the default answer for everything, for scripts and other robots.
    --no-verify (or CARZTY_NO_VERIFY=1) skips the "ask Discord about the token" part.

Notes:
    Author: Zachary Wright (xchronusx)
    Output is plain ASCII on purpose. Old Windows consoles and emoji do not get along.
    The Discord check is best effort. No internet? It saves the token anyway and tells you.
"""

from __future__ import annotations

import base64
import getpass
import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from carzty import __version__
from carzty.config import ROOT, TONES

API = "https://discord.com/api/v10"
USER_AGENT = f"DiscordBot (https://github.com/xchronusx/carzty, {__version__})"
# View Channel + Send Messages + Send Messages in Threads + Embed Links. nothing scary.
INVITE_PERMISSIONS = 274877926400

_TOKEN_SHAPE = re.compile(r"^[A-Za-z0-9_\-]{17,}\.[A-Za-z0-9_\-]{4,}\.[A-Za-z0-9_\-]{20,}$")

MINIMAL_ENV = [
    "##xchronusx",
    "# Carzty config. Every setting is listed at https://github.com/xchronusx/carzty#config",
    "DISCORD_TOKEN=",
    "DEFAULT_TIMEZONE=UTC",
    "DEFAULT_TONE=salty",
    "ALLOWED_USER_IDS=",
    "##xchronusx",
]

#region WINDOWS TIMEZONES

# Windows uses its own timezone names because of course it does. These are the common ones.
WINDOWS_TO_IANA = {
    "Dateline Standard Time": "Etc/GMT+12",
    "Hawaiian Standard Time": "Pacific/Honolulu",
    "Alaskan Standard Time": "America/Anchorage",
    "Pacific Standard Time": "America/Los_Angeles",
    "US Mountain Standard Time": "America/Phoenix",
    "Mountain Standard Time": "America/Denver",
    "Central Standard Time": "America/Chicago",
    "Central America Standard Time": "America/Guatemala",
    "Canada Central Standard Time": "America/Regina",
    "Central Standard Time (Mexico)": "America/Mexico_City",
    "Eastern Standard Time": "America/New_York",
    "US Eastern Standard Time": "America/Indianapolis",
    "SA Pacific Standard Time": "America/Bogota",
    "Atlantic Standard Time": "America/Halifax",
    "Newfoundland Standard Time": "America/St_Johns",
    "E. South America Standard Time": "America/Sao_Paulo",
    "Argentina Standard Time": "America/Buenos_Aires",
    "UTC": "UTC",
    "GMT Standard Time": "Europe/London",
    "Greenwich Standard Time": "Atlantic/Reykjavik",
    "W. Europe Standard Time": "Europe/Berlin",
    "Romance Standard Time": "Europe/Paris",
    "Central Europe Standard Time": "Europe/Budapest",
    "Central European Standard Time": "Europe/Warsaw",
    "GTB Standard Time": "Europe/Bucharest",
    "FLE Standard Time": "Europe/Kiev",
    "E. Europe Standard Time": "Europe/Chisinau",
    "Turkey Standard Time": "Europe/Istanbul",
    "Israel Standard Time": "Asia/Jerusalem",
    "South Africa Standard Time": "Africa/Johannesburg",
    "Russian Standard Time": "Europe/Moscow",
    "Arabian Standard Time": "Asia/Dubai",
    "Pakistan Standard Time": "Asia/Karachi",
    "India Standard Time": "Asia/Calcutta",
    "Bangladesh Standard Time": "Asia/Dhaka",
    "SE Asia Standard Time": "Asia/Bangkok",
    "China Standard Time": "Asia/Shanghai",
    "Singapore Standard Time": "Asia/Singapore",
    "Taipei Standard Time": "Asia/Taipei",
    "Tokyo Standard Time": "Asia/Tokyo",
    "Korea Standard Time": "Asia/Seoul",
    "AUS Central Standard Time": "Australia/Darwin",
    "Cen. Australia Standard Time": "Australia/Adelaide",
    "E. Australia Standard Time": "Australia/Brisbane",
    "AUS Eastern Standard Time": "Australia/Sydney",
    "West Pacific Standard Time": "Pacific/Port_Moresby",
    "New Zealand Standard Time": "Pacific/Auckland",
}

#endregion


#region HELPERS

class TokenRejected(Exception):
    """Discord looked at the token and said 401."""


@dataclass(frozen=True)
class AppInfo:
    id: str | None
    name: str | None = None
    owner_id: str | None = None
    owner_name: str | None = None


def looks_like_token(token: str) -> bool:
    return bool(_TOKEN_SHAPE.match(token or ""))


def app_id_from_token(token: str) -> str | None:
    """The first chunk of a bot token is just the bot's id in base64. handy for building the invite link offline."""
    try:
        first = token.split(".")[0]
        decoded = base64.urlsafe_b64decode(first + "=" * (-len(first) % 4)).decode()
        return decoded if decoded.isdigit() else None
    except (ValueError, UnicodeDecodeError, IndexError):
        return None


def fetch_app(token: str, timeout: float = 10) -> AppInfo:
    """Ask Discord who this token belongs to. Raises TokenRejected on a bad token, OSError if offline."""
    req = urllib.request.Request(
        f"{API}/oauth2/applications/@me",
        headers={"Authorization": f"Bot {token}", "User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - hardcoded https url
            data = json.load(resp)
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise TokenRejected() from None
        raise OSError(f"Discord answered HTTP {exc.code}") from None

    team = data.get("team")
    if team:
        owner_id = str(team.get("owner_user_id") or "") or None
        owner_name = f"team {team.get('name')}"
    else:
        owner = data.get("owner") or {}
        owner_id = str(owner.get("id") or "") or None
        owner_name = owner.get("global_name") or owner.get("username")
    return AppInfo(id=str(data.get("id")), name=data.get("name"), owner_id=owner_id, owner_name=owner_name)


def _valid_zone(name: str | None) -> str | None:
    if not name:
        return None
    try:
        ZoneInfo(name)
        return name
    except (ZoneInfoNotFoundError, ValueError):
        return None


def detect_timezone() -> str | None:
    """Best guess at the machine's IANA timezone. None if it can't tell."""
    tz = _valid_zone(os.environ.get("TZ", "").lstrip(":"))
    if tz:
        return tz

    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\TimeZoneInformation") as key:
                win_name = winreg.QueryValueEx(key, "TimeZoneKeyName")[0]
            return _valid_zone(WINDOWS_TO_IANA.get(str(win_name).strip("\x00 ")))
        except OSError:
            return None

    try:
        tz = _valid_zone(Path("/etc/timezone").read_text().strip())
        if tz:
            return tz
    except OSError:
        pass
    try:
        target = os.path.realpath("/etc/localtime")
        if "zoneinfo/" in target:
            return _valid_zone(target.split("zoneinfo/", 1)[1])
    except OSError:
        pass
    return None


def invite_links(app_id: str) -> tuple[str, str]:
    server = (
        f"https://discord.com/oauth2/authorize?client_id={app_id}"
        f"&scope=bot+applications.commands&permissions={INVITE_PERMISSIONS}"
    )
    user = f"https://discord.com/oauth2/authorize?client_id={app_id}&integration_type=1&scope=applications.commands"
    return server, user

#endregion


#region .ENV FILE

def get_env(lines: list[str], key: str) -> str | None:
    for line in lines:
        m = re.match(rf"^\s*{re.escape(key)}\s*=(.*)$", line)
        if m:
            return m.group(1).strip().strip('"').strip("'")
    return None


def set_env(lines: list[str], key: str, value: str) -> list[str]:
    out, found = [], False
    for line in lines:
        if not found and re.match(rf"^\s*{re.escape(key)}\s*=", line):
            out.append(f"{key}={value}")
            found = True
        else:
            out.append(line)
    if not found:
        # tuck it in before the closing signature if there is one
        if out and out[-1].strip() == "##xchronusx":
            out.insert(len(out) - 1, f"{key}={value}")
        else:
            out.append(f"{key}={value}")
    return out


def write_env(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # utf-8, no BOM, unix newlines. python-dotenv is happy, notepad is happy, everyone's happy
    path.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8", newline="\n")
    if os.name == "posix":
        os.chmod(path, 0o600)  # it's got a token in it. nobody else needs to read it


def starting_lines(env_path: Path) -> list[str]:
    if env_path.exists():
        return env_path.read_text(encoding="utf-8-sig").splitlines()
    example = ROOT / ".env.example"
    if example.exists():
        return example.read_text(encoding="utf-8-sig").splitlines()
    return list(MINIMAL_ENV)

#endregion


class Wizard:
    def __init__(
        self,
        env_path: Path,
        ask: Callable[[str], str] = input,
        ask_secret: Callable[[str], str] = getpass.getpass,
        say: Callable[[str], None] = print,
        fetch: Callable[[str], AppInfo] = fetch_app,
        detect_tz: Callable[[], str | None] = detect_timezone,
        yes: bool = False,
        verify: bool = True,
    ) -> None:
        self.env_path = env_path
        self.ask = ask
        self.ask_secret = ask_secret
        self.say = say
        self.fetch = fetch
        self.detect_tz = detect_tz
        self.yes = yes
        self.verify = verify

    #region PROMPTS

    def confirm(self, question: str, default: bool = True) -> bool:
        if self.yes:
            return default
        hint = "[Y/n]" if default else "[y/N]"
        while True:
            answer = self.ask(f"{question} {hint} ").strip().lower()
            if not answer:
                return default
            if answer in ("y", "yes", "yep", "yeah", "sure"):
                return True
            if answer in ("n", "no", "nope", "nah"):
                return False
            self.say("  y or n. it's not a trick question.")

    #endregion

    #region STEPS

    def step_token(self, lines: list[str], token: str | None) -> tuple[str, AppInfo] | None:
        self.say("")
        self.say("1/4  Bot token")
        current = get_env(lines, "DISCORD_TOKEN") or ""
        have_current = looks_like_token(current)

        if token:
            candidates = [token.strip()]
        elif have_current and self.confirm("  There's already a token in your .env. Keep it?", True):
            candidates = [current]
        elif self.yes:
            self.say("  No token given. Run it again with --token, or without --yes so I can ask.")
            return None
        else:
            self.say("  Developer Portal -> your app -> Bot -> Reset Token. Don't have an app yet?")
            self.say("  https://github.com/xchronusx/carzty/blob/main/docs/discord-setup.md walks you through it.")
            candidates = []

        for attempt in range(3):
            if attempt < len(candidates):
                candidate = candidates[attempt]
            elif self.yes or token:
                return None
            else:
                candidate = self.ask_secret("  Paste the token (it won't show up while you paste, that's on purpose): ").strip()

            if not looks_like_token(candidate):
                self.say("  That doesn't look like a bot token. It's three chunks separated by dots, about 70 characters.")
                continue

            if not self.verify:
                self.say("  not checking it with Discord (--no-verify). hope you pasted it right.")
                return candidate, AppInfo(id=app_id_from_token(candidate))
            try:
                app = self.fetch(candidate)
                self.say(f"  ok - that's the token for '{app.name}'.")
                return candidate, app
            except TokenRejected:
                self.say("  Discord says that token is no good. Reset it in the portal and paste the new one.")
            except OSError as exc:
                self.say(f"  Couldn't reach Discord to double-check it ({exc}). Saving it anyway.")
                return candidate, AppInfo(id=app_id_from_token(candidate))

        self.say("  Three strikes. Go grab a fresh token and run `carzty setup` again.")
        return None

    def step_timezone(self, lines: list[str], timezone: str | None) -> str:
        self.say("")
        self.say("2/4  Timezone (so '9am' means YOUR 9am)")
        if timezone:
            if _valid_zone(timezone):
                self.say(f"  using {timezone}")
                return timezone
            self.say(f"  '{timezone}' isn't a real timezone, so I'll ask.")

        detected = self.detect_tz()
        current = _valid_zone(get_env(lines, "DEFAULT_TIMEZONE"))
        guess = detected or (current if current and current != "UTC" else None)
        if guess and self.confirm(f"  Looks like you're in {guess}. Use that?", True):
            if self.yes:
                self.say(f"  using {guess}")
            return guess
        if self.yes:
            self.say("  using UTC")
            return "UTC"

        while True:
            answer = self.ask("  Timezone, like America/Phoenix or Europe/London (blank = UTC): ").strip()
            if not answer:
                return "UTC"
            zone = _valid_zone(answer) or _valid_zone(answer.replace(" ", "_"))
            if zone:
                return zone
            self.say("  Not a timezone I know. Format is Region/City: America/Chicago, Asia/Tokyo...")

    def step_tone(self, lines: list[str], tone: str | None) -> str:
        self.say("")
        self.say("3/4  Tone")
        if tone and tone.lower() in TONES:
            return tone.lower()
        current = (get_env(lines, "DEFAULT_TONE") or "salty").lower()
        default = current if current in TONES else "salty"
        if self.yes:
            self.say(f"  using {default}")
            return default
        self.say("  1) chill     polite. grandma-safe")
        self.say("  2) salty     sarcastic, mostly clean")
        self.say("  3) unhinged  swears at you. you've been warned")
        pick = {"1": "chill", "2": "salty", "3": "unhinged"}
        while True:
            answer = self.ask(f"  Pick one [{TONES.index(default) + 1}]: ").strip().lower()
            if not answer:
                return default
            if answer in pick:
                return pick[answer]
            if answer in TONES:
                return answer
            self.say("  1, 2 or 3.")

    def step_lock(self, app: AppInfo, lock: bool | None) -> str | None:
        """Returns the new ALLOWED_USER_IDS value, or None to leave it alone."""
        self.say("")
        self.say("4/4  Who gets to use it")
        if not app.owner_id:
            self.say("  Couldn't look up who owns the bot, so I'll leave this alone. (ALLOWED_USER_IDS in .env)")
            return None
        who = app.owner_name or app.owner_id
        if lock is None:
            lock = self.confirm(f"  Lock it so only {who} can use it? Say no if friends are gonna use it too.", True)
        if lock:
            return app.owner_id
        return ""

    #endregion

    def run(self, token: str | None = None, timezone: str | None = None, tone: str | None = None, lock: bool | None = None) -> int:
        self.say("")
        self.say("=" * 60)
        self.say(f"  Carzty v{__version__} setup. Four questions, then you're done.")
        self.say("=" * 60)

        lines = starting_lines(self.env_path)

        got = self.step_token(lines, token)
        if got is None:
            return 2
        token_value, app = got
        lines = set_env(lines, "DISCORD_TOKEN", token_value)

        tz = self.step_timezone(lines, timezone)
        lines = set_env(lines, "DEFAULT_TIMEZONE", tz)

        lines = set_env(lines, "DEFAULT_TONE", self.step_tone(lines, tone))

        allowed = self.step_lock(app, lock)
        if allowed is not None:
            lines = set_env(lines, "ALLOWED_USER_IDS", allowed)

        write_env(self.env_path, lines)

        self.say("")
        self.say("-" * 60)
        self.say(f"  Saved: {self.env_path}")
        app_id = app.id or app_id_from_token(token_value)
        if app_id:
            server, user = invite_links(app_id)
            self.say("")
            self.say("  Add it to a server:")
            self.say(f"    {server}")
            self.say("  Or add it to your account so /task works everywhere (turn on 'User Install'")
            self.say("  under Installation in the developer portal first):")
            self.say(f"    {user}")
        self.say("-" * 60)
        return 0


def run_setup(env_path: Path, **kwargs) -> int:
    yes = kwargs.pop("yes", False)
    verify = kwargs.pop("verify", True) and os.environ.get("CARZTY_NO_VERIFY", "") not in ("1", "true", "yes")
    try:
        return Wizard(env_path, yes=yes, verify=verify).run(**kwargs)
    except (KeyboardInterrupt, EOFError):
        print("\n  Bailed. Nothing was saved.")
        return 130
##xchronusx
