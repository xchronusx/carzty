##xchronusx
"""
tests/test_flows.py - drive the real slash command + button callbacks with a fake interaction.

Description:
    No Discord connection. We build a real CarztyBot (never logged in), load the
    cogs, and poke the command callbacks directly with a FakeInteraction that
    records whatever the bot tries to say. Catches the dumb stuff: wrong kwargs,
    bad state handling, replies that never get sent.

Notes:
    Author: Zachary Wright (xchronusx)
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from types import SimpleNamespace

import discord
import pytest
from discord import app_commands
from discord.app_commands import Choice

from carzty.bot import CarztyBot
from carzty.config import Config
from carzty.core import engine
from carzty.core.models import DELIVER_CHANNEL, DELIVER_DM, DONE
from carzty.core.store import Store
from carzty.errors import Oops
from carzty.ui.buttons import DoneButton, SnoozeButton

USER = 111


class FakeResponse:
    def __init__(self, sink):
        self.sink = sink
        self._done = False

    def is_done(self):
        return self._done

    async def send_message(self, content=None, **kw):
        self._done = True
        self.sink.append(("send", content, kw))

    async def edit_message(self, **kw):
        self._done = True
        self.sink.append(("edit", None, kw))


class FakeFollowup:
    def __init__(self, sink):
        self.sink = sink

    async def send(self, content=None, **kw):
        self.sink.append(("followup", content, kw))


class FakeInteraction:
    def __init__(self, bot, user_id=USER, guild=True, guild_install=True, perms=None, message=None):
        self.client = bot
        self.user = SimpleNamespace(id=user_id, display_name="tester")
        self.sent = []
        self.response = FakeResponse(self.sent)
        self.followup = FakeFollowup(self.sent)
        self.guild = SimpleNamespace(id=1) if guild else None
        self.guild_id = 1 if guild else None
        self.channel_id = 50 if guild else 9
        self.channel = SimpleNamespace(id=self.channel_id)
        self._guild_install = guild_install
        self.app_permissions = perms or discord.Permissions(view_channel=True, send_messages=True, embed_links=True)
        self.message = message
        self.command = None

    def is_guild_integration(self):
        return self._guild_install

    @property
    def last(self):
        return self.sent[-1]

    def text(self):
        kind, content, kw = self.last
        if content:
            return content
        emb = kw.get("embed")
        return (emb.description or "") if emb else ""


@pytest.fixture
def bot():
    async def build():
        b = CarztyBot(Config(token="x", default_tz="America/Phoenix"), Store(":memory:"))
        for cog in ("carzty.cogs.task_commands", "carzty.cogs.carzty_commands"):
            await b.load_extension(cog)
        return b

    b = asyncio.run(build())
    yield b
    b.store.close()


def _cmd(bot, path):
    cmd = bot.tree.get_command(path.split()[0])
    for part in path.split()[1:]:
        cmd = cmd.get_command(part)
    return cmd


def run(bot, path, interaction=None, **kwargs):
    """Call /<path> like Discord would, including the tree's error handler."""
    interaction = interaction or FakeInteraction(bot)
    cmd = _cmd(bot, path)

    async def go():
        try:
            await cmd.callback(cmd.binding, interaction, **kwargs)
        except Exception as exc:  # noqa: BLE001
            err = exc if isinstance(exc, app_commands.AppCommandError) else app_commands.CommandInvokeError(cmd, exc)
            await bot.tree.on_error(interaction, err)

    asyncio.run(go())
    return interaction


#region ADD


def test_add_recurring_with_nag(bot):
    i = run(bot, "task add", what="Take meds", every="1d", when="9am", nag="10m")
    kind, _, kw = i.last
    assert kind == "send" and kw["ephemeral"] is True
    tasks = bot.store.list_for_user(USER)
    assert len(tasks) == 1
    t = tasks[0]
    assert t.interval_seconds == 86400 and t.nag_seconds == 600 and t.tz == "America/Phoenix"
    assert t.next_due > engine.utcnow()
    assert "Reading times as" in kw["embed"].description  # no saved tz yet, so we warn


def test_add_one_shot_needs_when(bot):
    i = run(bot, "task add", what="Call dentist")
    assert i.text().startswith("❌") and "when" in i.text()
    assert bot.store.count_open(USER) == 0


def test_add_rejects_tiny_interval(bot):
    i = run(bot, "task add", what="spam", every="10s")
    assert i.text().startswith("❌") and "Minimum" in i.text()


def test_add_rejects_bad_when(bot):
    i = run(bot, "task add", what="x", when="the day after never")
    assert i.text().startswith("❌")


def test_add_deliver_channel(bot):
    run(bot, "task add", what="Standup", every="weekdays", deliver=Choice(name="here", value=DELIVER_CHANNEL))
    t = bot.store.list_for_user(USER)[0]
    assert t.deliver == DELIVER_CHANNEL and t.channel_id == 50 and t.weekdays == (0, 1, 2, 3, 4)


def test_add_deliver_channel_as_user_app_falls_back(bot):
    i = FakeInteraction(bot, guild_install=False)
    run(bot, "task add", interaction=i, what="x", every="1h", deliver=Choice(name="here", value=DELIVER_CHANNEL))
    t = bot.store.list_for_user(USER)[0]
    assert t.deliver == DELIVER_DM
    assert "user app" in i.last[2]["embed"].description


def test_add_deliver_channel_without_perms_falls_back(bot):
    i = FakeInteraction(bot, perms=discord.Permissions(view_channel=True))
    run(bot, "task add", interaction=i, what="x", every="1h", deliver=Choice(name="here", value=DELIVER_CHANNEL))
    assert bot.store.list_for_user(USER)[0].deliver == DELIVER_DM


def test_task_limit(bot):
    bot.config = Config(token="x", max_tasks_per_user=2)
    for n in range(2):
        run(bot, "task add", what=f"t{n}", every="1h")
    i = run(bot, "task add", what="one too many", every="1h")
    assert i.text().startswith("❌") and bot.store.count_open(USER) == 2

#endregion


#region MANAGE


def _add(bot, **kw):
    kw.setdefault("what", "drink water")
    kw.setdefault("every", "1h")
    run(bot, "task add", **kw)
    return bot.store.list_for_user(USER)[0]


def test_list_and_show(bot):
    t = _add(bot)
    i = run(bot, "task list")
    assert f"#{t.id}" in i.last[2]["embed"].description
    i = run(bot, "task show", task=t.id)
    assert i.last[2]["embed"].title == "drink water"


def test_other_users_cant_see_my_task(bot):
    t = _add(bot)
    i = run(bot, "task show", interaction=FakeInteraction(bot, user_id=222), task=t.id)
    assert i.text().startswith("❌")
    i = run(bot, "task remove", interaction=FakeInteraction(bot, user_id=222), task=t.id)
    assert bot.store.get(t.id) is not None


def test_done_early_then_snooze_errors(bot):
    t = _add(bot, every="1d", when="9am")
    i = run(bot, "task done", task=t.id)
    assert i.text().startswith("✅") and "Next reminder" in i.text()
    assert bot.store.get(t.id).next_due == t.next_due + 86400  # phoenix, no DST, so exactly a day
    i = run(bot, "task snooze", task=t.id, duration="15m")
    assert i.text().startswith("❌") and "snooze" in i.text().lower()


def test_ringing_task_full_cycle(bot):
    t = _add(bot, every="1h", nag="5m")
    now = engine.utcnow()
    fired_task, _ = engine.process(replace(t, next_due=now), now)
    bot.store.save(fired_task)

    i = run(bot, "task snooze", task=t.id, duration="tomorrow 9am")
    assert i.text().startswith("💤")
    assert bot.store.get(t.id).followup_kind == "snooze"

    i = run(bot, "task done", task=t.id)
    assert i.text().startswith("✅")
    after = bot.store.get(t.id)
    assert not after.pending and after.times_done == 1


def test_pause_resume_skip_remove(bot):
    t = _add(bot)
    assert run(bot, "task pause", task=t.id).text().startswith("⏸️")
    assert run(bot, "task pause", task=t.id).text().startswith("❌")
    assert run(bot, "task resume", task=t.id).text().startswith("▶️")
    assert run(bot, "task skip", task=t.id).text().startswith("⏭️")
    assert run(bot, "task remove", task=t.id).text().startswith("🗑️")
    assert bot.store.get(t.id) is None


def test_edit(bot):
    t = _add(bot)
    assert run(bot, "task edit", task=t.id).text().startswith("❌")  # changed nothing
    run(bot, "task edit", task=t.id, what="drink coffee", every="weekdays", when="8am", nag="15m", notes="the good stuff")
    e = bot.store.get(t.id)
    assert (e.title, e.weekdays, e.nag_seconds, e.notes) == ("drink coffee", (0, 1, 2, 3, 4), 900, "the good stuff")
    run(bot, "task edit", task=t.id, nag="off", notes="clear")
    e = bot.store.get(t.id)
    assert e.nag_seconds is None and e.notes is None


def test_edit_revives_done_one_shot(bot):
    run(bot, "task add", what="once", when="in 1h")
    t = bot.store.list_for_user(USER)[0]
    run(bot, "task done", task=t.id)
    assert bot.store.get(t.id).state == DONE
    run(bot, "task edit", task=t.id, when="tomorrow 3pm")
    assert bot.store.get(t.id).state == "active"

#endregion


#region SETTINGS + ERRORS


def test_timezone_and_tone(bot):
    i = run(bot, "carzty timezone", zone="Europe/London")
    assert "Europe/London" in i.text()
    assert bot.user_tz(USER) == "Europe/London"
    assert run(bot, "carzty timezone", zone="Narnia/Cair_Paravel").text().startswith("❌")
    run(bot, "carzty tone", tone=Choice(name="x", value="chill"))
    assert bot.user_tone(USER) == "chill"
    run(bot, "carzty me")
    run(bot, "carzty help")


def test_unexpected_errors_get_a_generic_reply(bot):
    i = FakeInteraction(bot)
    cmd = _cmd(bot, "task list")
    asyncio.run(bot.tree.on_error(i, app_commands.CommandInvokeError(cmd, RuntimeError("kaboom"))))
    assert "Something broke" in i.text()


def test_user_errors_reply_once(bot):
    i = FakeInteraction(bot)
    cmd = _cmd(bot, "task list")
    asyncio.run(bot.tree.on_error(i, app_commands.CommandInvokeError(cmd, Oops("nah"))))
    assert len(i.sent) == 1 and i.text() == "❌ nah"


def test_allowlist(bot):
    bot.config = Config(token="x", allowed_user_ids=frozenset({999}))
    i = FakeInteraction(bot)
    assert asyncio.run(bot.tree.interaction_check(i)) is False
    assert "private" in i.text()

#endregion


#region BUTTONS


def _ringing(bot, **kw):
    t = _add(bot, **kw)
    now = engine.utcnow()
    fired, _ = engine.process(replace(t, next_due=now), now)
    bot.store.save(fired)
    return fired


def _button_interaction(bot, user_id=USER):
    msg = SimpleNamespace(embeds=[discord.Embed(title="🔔 drink water")])
    return FakeInteraction(bot, user_id=user_id, message=msg)


def test_done_button(bot):
    t = _ringing(bot)
    i = _button_interaction(bot)
    asyncio.run(DoneButton(t.id).callback(i))
    kind, _, kw = i.sent[0]
    assert kind == "edit" and kw["view"] is None
    assert any(f.name == "Status" and "Done" in f.value for f in kw["embed"].fields)
    assert not bot.store.get(t.id).pending
    # pressing it again on the same message just tidies up
    i2 = _button_interaction(bot)
    asyncio.run(DoneButton(t.id).callback(i2))
    assert i2.sent[-1][0] == "followup" and "Already handled" in i2.sent[-1][1]


def test_snooze_button(bot):
    t = _ringing(bot)
    i = _button_interaction(bot)
    asyncio.run(SnoozeButton(t.id, 900).callback(i))
    assert bot.store.get(t.id).followup_kind == "snooze"


def test_buttons_are_owner_only(bot):
    t = _ringing(bot)
    i = _button_interaction(bot, user_id=222)
    asyncio.run(DoneButton(t.id).callback(i))
    assert i.sent[0][0] == "send" and i.sent[0][2]["ephemeral"]
    assert bot.store.get(t.id).pending  # untouched


def test_button_for_deleted_task(bot):
    i = _button_interaction(bot)
    asyncio.run(DoneButton(424242).callback(i))
    assert i.sent[0][0] == "edit" and "doesn't exist" in i.sent[1][1]

#endregion
##xchronusx
