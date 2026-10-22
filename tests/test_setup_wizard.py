##xchronusx
"""
tests/test_setup_wizard.py - the wizard, with a fake human typing into it.

Notes:
    Author: Zachary Wright (xchronusx)
    No network. fetch_app gets swapped for a stub every time.
"""

from __future__ import annotations

import base64

import pytest

from carzty.config import app_home
from carzty.setup_wizard import (
    AppInfo,
    TokenRejected,
    Wizard,
    app_id_from_token,
    get_env,
    invite_links,
    looks_like_token,
    set_env,
)

APP_ID = "123456789012345678"
GOOD = base64.urlsafe_b64encode(APP_ID.encode()).decode().rstrip("=") + ".GhJkLm.abcdefghijklmnopqrstuvwxyz0123456789AB"
GOOD2 = base64.urlsafe_b64encode(b"987654321098765432").decode().rstrip("=") + ".XyZaBc.zyxwvutsrqponmlkjihgfedcba9876543210"


class Human:
    """Feeds canned answers to the wizard and records everything it says."""

    def __init__(self, *answers, secrets=()):
        self.answers = list(answers)
        self.secrets = list(secrets)
        self.heard: list[str] = []

    def ask(self, prompt):
        self.heard.append(prompt)
        return self.answers.pop(0)

    def ask_secret(self, prompt):
        self.heard.append(prompt)
        return self.secrets.pop(0)

    def say(self, line):
        self.heard.append(line)

    @property
    def transcript(self):
        return "\n".join(self.heard)


def ok_fetch(_token):
    return AppInfo(id=APP_ID, name="Carzty Test", owner_id="42", owner_name="xchronusx")


def wizard(tmp_path, human, fetch=ok_fetch, tz="America/Phoenix", yes=False):
    return Wizard(
        tmp_path / ".env",
        ask=human.ask,
        ask_secret=human.ask_secret,
        say=human.say,
        fetch=fetch,
        detect_tz=lambda: tz,
        yes=yes,
    )


def read_env(tmp_path):
    return (tmp_path / ".env").read_text().splitlines()


#region HELPERS


def test_token_helpers():
    assert looks_like_token(GOOD)
    assert not looks_like_token("paste-your-token-here")
    assert not looks_like_token("")
    assert app_id_from_token(GOOD) == APP_ID
    assert app_id_from_token("garbage") is None


def test_env_helpers_keep_comments():
    lines = ["# hi", "DISCORD_TOKEN=old", "##xchronusx"]
    lines = set_env(lines, "DISCORD_TOKEN", "new")
    lines = set_env(lines, "DEFAULT_TONE", "chill")
    assert lines == ["# hi", "DISCORD_TOKEN=new", "DEFAULT_TONE=chill", "##xchronusx"]
    assert get_env(lines, "DISCORD_TOKEN") == "new"
    assert get_env(lines, "NOPE") is None


def test_invite_links():
    server, user = invite_links(APP_ID)
    assert f"client_id={APP_ID}" in server and "scope=bot+applications.commands" in server and "permissions=274877926400" in server
    assert "integration_type=1" in user


def test_app_home(tmp_path):
    assert app_home({"CARZTY_HOME": str(tmp_path)}) == tmp_path.resolve()
    # running from the repo checkout -> the repo folder
    assert (app_home({}) / "pyproject.toml").is_file()


@pytest.mark.parametrize(
    ("platform", "env", "tail"),
    [
        ("linux", {"XDG_DATA_HOME": "/xdg"}, ("xdg", "carzty")),
        ("linux", {}, (".local", "share", "carzty")),
        ("darwin", {}, ("Library", "Application Support", "Carzty")),
        ("win32", {"LOCALAPPDATA": "/lad"}, ("lad", "Carzty")),
    ],
)
def test_app_home_when_pip_installed(tmp_path, monkeypatch, platform, env, tail):
    import carzty.config as cfg

    monkeypatch.setattr(cfg, "ROOT", tmp_path)  # no pyproject.toml here, so it's not a checkout
    monkeypatch.setattr(cfg.sys, "platform", platform)
    assert app_home(env).parts[-len(tail):] == tail

#endregion


#region HAPPY PATHS


def test_full_interactive_run(tmp_path):
    human = Human("", "3", "", secrets=[GOOD])  # yes to detected tz, unhinged, yes lock
    code = wizard(tmp_path, human).run()
    assert code == 0
    env = read_env(tmp_path)
    assert get_env(env, "DISCORD_TOKEN") == GOOD
    assert get_env(env, "DEFAULT_TIMEZONE") == "America/Phoenix"
    assert get_env(env, "DEFAULT_TONE") == "unhinged"
    assert get_env(env, "ALLOWED_USER_IDS") == "42"
    assert get_env(env, "MAX_NAGS") == "24"  # started from .env.example, so the other settings are still there
    assert f"client_id={APP_ID}" in human.transcript
    assert "Carzty Test" in human.transcript


def test_non_interactive(tmp_path):
    human = Human()
    code = wizard(tmp_path, human, yes=True).run(token=GOOD, timezone="Europe/London", tone="chill", lock=False)
    assert code == 0
    env = read_env(tmp_path)
    assert get_env(env, "DEFAULT_TIMEZONE") == "Europe/London"
    assert get_env(env, "DEFAULT_TONE") == "chill"
    assert get_env(env, "ALLOWED_USER_IDS") == ""


def test_rerun_keeps_existing_token(tmp_path):
    wizard(tmp_path, Human(), yes=True).run(token=GOOD, tone="chill")
    human = Human("", "", "", "")  # keep token, keep tz, keep tone, lock
    assert wizard(tmp_path, human).run() == 0
    env = read_env(tmp_path)
    assert get_env(env, "DISCORD_TOKEN") == GOOD
    assert get_env(env, "DEFAULT_TONE") == "chill"
    assert env.count(f"DISCORD_TOKEN={GOOD}") == 1


def test_offline_still_saves(tmp_path):
    def offline(_token):
        raise OSError("no internet, sorry")

    human = Human("", "", "", secrets=[GOOD])
    assert wizard(tmp_path, human, fetch=offline).run() == 0
    assert "Couldn't reach Discord" in human.transcript
    assert f"client_id={APP_ID}" in human.transcript  # invite link still built from the token itself
    assert "Couldn't look up who owns" in human.transcript

#endregion


#region SAD PATHS


def test_bad_then_good_token(tmp_path):
    def picky(token):
        if token == GOOD:
            raise TokenRejected()
        return ok_fetch(token)

    human = Human("", "", "n", secrets=["nope", GOOD, GOOD2])
    assert wizard(tmp_path, human, fetch=picky).run() == 0
    assert "doesn't look like a bot token" in human.transcript
    assert "Discord says that token is no good" in human.transcript
    assert get_env(read_env(tmp_path), "DISCORD_TOKEN") == GOOD2
    assert get_env(read_env(tmp_path), "ALLOWED_USER_IDS") == ""


def test_three_strikes(tmp_path):
    human = Human(secrets=["a", "b", "c"])
    assert wizard(tmp_path, human).run() == 2
    assert not (tmp_path / ".env").exists()


def test_yes_without_token_fails(tmp_path):
    assert wizard(tmp_path, Human(), yes=True).run() == 2


def test_manual_timezone_entry(tmp_path):
    # say no to the detected one, type garbage, then type it with a space instead of an underscore
    human = Human("n", "Mars/Base", "America/New York", "", "", secrets=[GOOD])
    assert wizard(tmp_path, human).run() == 0
    assert get_env(read_env(tmp_path), "DEFAULT_TIMEZONE") == "America/New_York"
    assert "Not a timezone I know" in human.transcript


def test_no_detected_tz_blank_means_utc(tmp_path):
    human = Human("", "", "", secrets=[GOOD])
    assert wizard(tmp_path, human, tz=None).run() == 0
    assert get_env(read_env(tmp_path), "DEFAULT_TIMEZONE") == "UTC"


@pytest.mark.parametrize("answer", ["maybe", "idk"])
def test_confirm_nags_for_real_answer(tmp_path, answer):
    human = Human(answer, "y")
    assert wizard(tmp_path, human).confirm("ok?") is True
    assert "not a trick question" in human.transcript

#endregion
##xchronusx
