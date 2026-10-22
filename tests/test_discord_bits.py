##xchronusx
"""
tests/test_discord_bits.py - the parts that touch discord.py, tested without actually logging in.

Description:
    * builds the real command tree and checks the payload against Discord's rules
      (name format, description lengths, option ordering...) so a bad command gets
      caught here instead of as a 400 on startup
    * runs the scheduler against a fake bot to check delivery + DM fallback
    * makes sure the button custom_ids round-trip through their templates

Notes:
    Author: Zachary Wright (xchronusx)
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import replace
from types import SimpleNamespace

import discord
import pytest

from carzty.bot import CarztyBot
from carzty.config import Config
from carzty.core.engine import Fired
from carzty.core.models import DELIVER_CHANNEL
from carzty.core.store import Store
from carzty.scheduler import Scheduler
from carzty.ui import render
from carzty.ui.buttons import DoneButton, SkipButton, SnoozeButton, reminder_view
from tests.conftest import NOW

NAME_RE = re.compile(r"^[-_\w]{1,32}$")

#region COMMAND TREE


@pytest.fixture
def payload():
    async def build():
        bot = CarztyBot(Config(token="x"), Store(":memory:"))
        for cog in ("carzty.cogs.task_commands", "carzty.cogs.carzty_commands"):
            await bot.load_extension(cog)
        out = bot.command_payload()
        bot.store.close()
        return out

    return asyncio.run(build())


def _walk_options(options, path):
    seen_optional = False
    for opt in options:
        where = f"{path} {opt['name']}"
        assert NAME_RE.match(opt["name"]) and opt["name"] == opt["name"].lower(), where
        assert 1 <= len(opt["description"]) <= 100, f"{where}: description is {len(opt['description'])} chars"
        if opt["type"] in (1, 2):  # subcommand / group
            assert len(opt.get("options", [])) <= 25, where
            _walk_options(opt.get("options", []), where)
            continue
        if opt.get("required"):
            assert not seen_optional, f"{where}: required option after an optional one"
        else:
            seen_optional = True
        assert len(opt.get("choices", [])) <= 25, where
        assert not (opt.get("choices") and opt.get("autocomplete")), f"{where}: choices + autocomplete can't mix"


def test_command_payload_is_valid(payload):
    names = {c["name"] for c in payload}
    assert names == {"task", "carzty"}
    for cmd in payload:
        assert NAME_RE.match(cmd["name"])
        assert 1 <= len(cmd["description"]) <= 100
        assert len(cmd["options"]) <= 25
        # user-installable + usable in DMs
        assert sorted(cmd["integration_types"]) == [0, 1]
        assert sorted(cmd["contexts"]) == [0, 1, 2]
        _walk_options(cmd["options"], cmd["name"])


def test_task_subcommands(payload):
    task = next(c for c in payload if c["name"] == "task")
    subs = {o["name"] for o in task["options"]}
    assert subs == {"add", "list", "show", "done", "snooze", "skip", "pause", "resume", "remove", "edit"}
    snooze = next(o for o in task["options"] if o["name"] == "snooze")
    assert [o["name"] for o in snooze["options"]] == ["task", "for"]

#endregion


#region BUTTONS


def test_button_ids_roundtrip(make_task):
    t = replace(make_task(interval_seconds=3600), id=77)
    view = reminder_view(t, (900, 3600))
    ids = [item.custom_id for item in view.children]
    assert ids == ["carzty:done:77", "carzty:snooze:77:900", "carzty:snooze:77:3600", "carzty:skip:77"]
    for cls, cid in ((DoneButton, ids[0]), (SnoozeButton, ids[1]), (SkipButton, ids[3])):
        assert cls.__discord_ui_compiled_template__.fullmatch(cid)


def test_one_shot_has_no_skip(make_task):
    t = replace(make_task(), id=5)
    assert all("skip" not in item.custom_id for item in reminder_view(t, (900,)).children)


def test_stamp_replaces_status():
    e = discord.Embed(title="x")
    e.add_field(name="Next nag", value="soon")
    e = render.stamp(e, "first")
    e = render.stamp(e, "second")
    assert [(f.name, f.value) for f in e.fields] == [("Status", "second")]

#endregion


#region SCHEDULER


class _Resp:
    status = 403
    reason = "Forbidden"


class FakeMessage:
    _next = 1000

    def __init__(self, channel_id, guild):
        FakeMessage._next += 1
        self.id = FakeMessage._next
        self.channel = SimpleNamespace(id=channel_id)
        self.guild = guild


class FakeChannel(discord.abc.Messageable):
    def __init__(self, cid, forbidden=False):
        self.id = cid
        self.forbidden = forbidden
        self.sent = []

    async def _get_channel(self):  # pragma: no cover - Messageable wants it, we never call it
        return self

    async def send(self, **kwargs):
        if self.forbidden:
            raise discord.Forbidden(_Resp(), "nope")
        self.sent.append(kwargs)
        return FakeMessage(self.id, guild=object())


class FakeUser:
    def __init__(self, uid, closed=False):
        self.id = uid
        self.closed = closed
        self.sent = []

    async def send(self, **kwargs):
        if self.closed:
            raise discord.Forbidden(_Resp(), "dms closed")
        self.sent.append(kwargs)
        return FakeMessage(9, guild=None)


class FakeBot:
    def __init__(self, store, channels=None, users=None):
        self.store = store
        self.config = Config(token="x")
        self.channels = channels or {}
        self.users = users or {}

    def user_tone(self, _uid):
        return "salty"

    def get_channel(self, cid):
        return self.channels.get(cid)

    async def fetch_channel(self, _cid):
        raise discord.NotFound(_Resp(), "gone")

    def get_user(self, uid):
        return self.users.get(uid)

    async def fetch_user(self, _uid):
        raise discord.NotFound(_Resp(), "who")


def _fired():
    return Fired("scheduled", 0, False, 0, False)


def test_tick_sends_dm_and_saves(store, make_task):
    user = FakeUser(111)
    bot = FakeBot(store, users={111: user})
    t = store.add(make_task(interval_seconds=3600, next_due=NOW - 1))
    sched = Scheduler(bot)
    # pin "now" so the test doesn't care what time it is when you run it
    import carzty.scheduler as mod

    real = mod.engine.utcnow
    mod.engine.utcnow = lambda: NOW
    try:
        sent = asyncio.run(sched.tick())
    finally:
        mod.engine.utcnow = real
    assert sent == 1 and len(user.sent) == 1
    saved = store.get(t.id)
    assert saved.pending and saved.next_due == NOW - 1 + 3600 and saved.last_message_id


def test_channel_forbidden_falls_back_to_dm(store, make_task):
    user = FakeUser(111)
    bot = FakeBot(store, channels={55: FakeChannel(55, forbidden=True)}, users={111: user})
    t = store.add(make_task(next_due=NOW, deliver=DELIVER_CHANNEL, channel_id=55, guild_id=1))
    out = asyncio.run(Scheduler(bot).deliver(t, _fired(), NOW))
    assert len(user.sent) == 1
    assert out.last_error and "DM" in out.last_error


def test_channel_post_mentions_owner_only(store, make_task):
    chan = FakeChannel(55)
    bot = FakeBot(store, channels={55: chan}, users={111: FakeUser(111)})
    t = store.add(make_task(next_due=NOW, deliver=DELIVER_CHANNEL, channel_id=55, guild_id=1))
    out = asyncio.run(Scheduler(bot).deliver(t, _fired(), NOW))
    assert out.last_error is None
    kwargs = chan.sent[0]
    assert kwargs["content"] == "<@111>"
    assert kwargs["allowed_mentions"].everyone is False


def test_nowhere_to_send_records_error(store, make_task):
    bot = FakeBot(store, users={111: FakeUser(111, closed=True)})
    t = store.add(make_task(next_due=NOW))
    out = asyncio.run(Scheduler(bot).deliver(t, _fired(), NOW))
    assert out.last_error and "DM" in out.last_error
    assert out.last_message_id is None

#endregion


#region COMMAND SYNC


def _bot_with_cogs():
    async def build():
        bot = CarztyBot(Config(token="x"), Store(":memory:"))
        for cog in ("carzty.cogs.task_commands", "carzty.cogs.carzty_commands"):
            await bot.load_extension(cog)
        return bot

    return asyncio.run(build())


def test_sync_only_when_commands_change():
    bot = _bot_with_cogs()
    calls = []

    async def fake_sync():
        calls.append(1)
        return [1, 2]

    bot.tree.sync = fake_sync

    async def go():
        return [await bot.sync_commands(), await bot.sync_commands(), await bot.sync_commands(force=True)]

    assert asyncio.run(go()) == [True, False, True]
    assert len(calls) == 2


def test_sync_failure_doesnt_kill_the_bot():
    bot = _bot_with_cogs()

    async def broken_sync():
        raise discord.HTTPException(_Resp(), "discord said no")

    bot.tree.sync = broken_sync
    assert asyncio.run(bot.sync_commands()) is False
    assert bot.store.get_meta("command_hash") is None  # so it tries again next time

#endregion
##xchronusx
