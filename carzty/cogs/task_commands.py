##xchronusx
"""
carzty.cogs.task_commands - every /task slash command.

Synopsis:
    /task add what:<text> [every] [when] [nag] [deliver] [notes]
    /task list [show_done]
    /task show|done|skip|pause|resume|remove task:<pick one>
    /task snooze task:<pick one> for:<15m | 1h | 5pm | tomorrow 9am>
    /task edit task:<pick one> [what] [every] [when] [nag] [deliver] [notes]

Description:
    Thin layer. Parse what the human typed, hand it to the engine, save the
    result, say something snarky. All replies are ephemeral (only you see them)
    so the bot doesn't spam a shared channel every time you check your list.

    The `task` option autocompletes from YOUR tasks, so you never need to know
    an id. If you type a raw number it still works.

Notes:
    Author: Zachary Wright (xchronusx)
    Discord gives us 3 seconds to respond to an interaction. Everything in here
    is local sqlite so that's never a problem, but don't go adding web calls in
    here without a defer().
"""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.app_commands import Choice, Range
from discord.ext import commands

from carzty.core import engine
from carzty.core.engine import EngineError
from carzty.core.models import ACTIVE, DELIVER_CHANNEL, DELIVER_DM, DONE, PAUSED, Task, get_zone
from carzty.core.timeparse import (
    ParseError,
    Schedule,
    format_duration,
    parse_duration,
    parse_every,
    parse_when,
)
from carzty.errors import Oops
from carzty.ui import render
from carzty.ui.buttons import reminder_view
from carzty.voice import say

if TYPE_CHECKING:
    from carzty.bot import CarztyBot

log = logging.getLogger("carzty.tasks")

OFF_WORDS = ("off", "none", "no", "never", "stop", "0", "-")
CLEAR_WORDS = ("none", "clear", "-", "remove", "delete")

EVERY_SUGGESTIONS = [
    ("once (one-time reminder)", "once"),
    ("every 30 minutes", "30m"),
    ("every hour", "1h"),
    ("every 2 hours", "2h"),
    ("every day", "1d"),
    ("weekdays (mon-fri)", "weekdays"),
    ("weekends", "weekends"),
    ("every week", "1w"),
    ("every other day", "2d"),
    ("mon, wed & fri", "mon,wed,fri"),
    ("tue & thu", "tue,thu"),
]
WHEN_SUGGESTIONS = [
    "now", "in 10m", "in 30m", "in 1h", "9am", "noon", "5pm", "tonight",
    "tomorrow 9am", "tomorrow morning", "monday 9am", "friday 5pm",
]
NAG_SUGGESTIONS = [
    ("off", "off"), ("every 5 minutes", "5m"), ("every 10 minutes", "10m"),
    ("every 15 minutes", "15m"), ("every 30 minutes", "30m"), ("every hour", "1h"),
]
SNOOZE_SUGGESTIONS = ["10m", "15m", "30m", "1h", "2h", "4h", "tonight", "tomorrow 9am"]

DELIVER_CHOICES = [
    Choice(name="DM me", value=DELIVER_DM),
    Choice(name="Post in this channel", value=DELIVER_CHANNEL),
]


#region AUTOCOMPLETE

def _short_status(task: Task, now: int) -> str:
    if task.state == DONE:
        return "done"
    if task.state == PAUSED:
        return "paused"
    if task.pending:
        return "ringing"
    if task.next_due:
        delta = task.next_due - now
        return f"in {format_duration(max(delta, 60) // 60 * 60)}" if delta > 0 else "any second"
    return "idle"


def _choices_for(bot: CarztyBot, user_id: int, current: str, include_done: bool) -> list[Choice[int]]:
    now = engine.utcnow()
    out = []
    for t in bot.store.search_for_user(user_id, current, include_done=include_done, limit=25):
        name = f"#{t.id} · {render.clip(t.title, 60)} · {_short_status(t, now)}"
        out.append(Choice(name=render.clip(name, 100), value=t.id))
    return out


async def open_task_autocomplete(interaction: discord.Interaction, current: str) -> list[Choice[int]]:
    return _choices_for(interaction.client, interaction.user.id, current, include_done=False)  # type: ignore[arg-type]


async def any_task_autocomplete(interaction: discord.Interaction, current: str) -> list[Choice[int]]:
    return _choices_for(interaction.client, interaction.user.id, current, include_done=True)  # type: ignore[arg-type]


def _text_choices(pairs: list[tuple[str, str]] | list[str], current: str) -> list[Choice[str]]:
    current = (current or "").strip()
    items = [(p, p) if isinstance(p, str) else p for p in pairs]
    picked = [Choice(name=n, value=v) for n, v in items if current.lower() in n.lower() or current.lower() in v.lower()]
    # always let them keep what they typed, even if it isn't one of ours
    if current and all(c.value != current for c in picked):
        picked.insert(0, Choice(name=render.clip(current, 100), value=current[:100]))
    return picked[:25]


async def every_autocomplete(interaction: discord.Interaction, current: str) -> list[Choice[str]]:  # noqa: ARG001
    return _text_choices(EVERY_SUGGESTIONS, current)


async def when_autocomplete(interaction: discord.Interaction, current: str) -> list[Choice[str]]:  # noqa: ARG001
    return _text_choices(WHEN_SUGGESTIONS, current)


async def nag_autocomplete(interaction: discord.Interaction, current: str) -> list[Choice[str]]:  # noqa: ARG001
    return _text_choices(NAG_SUGGESTIONS, current)


async def snooze_autocomplete(interaction: discord.Interaction, current: str) -> list[Choice[str]]:  # noqa: ARG001
    return _text_choices(SNOOZE_SUGGESTIONS, current)

#endregion


class TaskCommands(commands.Cog):
    """The /task group."""

    task = app_commands.Group(name="task", description="Tasks Carzty will bug you about")

    def __init__(self, bot: CarztyBot) -> None:
        self.bot = bot

    #region HELPERS

    def _schedule(self, every: str | None) -> Schedule:
        try:
            schedule = parse_every(every)
        except ParseError as exc:
            raise Oops(str(exc)) from None
        minimum = self.bot.config.min_interval
        if schedule.interval_seconds and schedule.interval_seconds < minimum:
            raise Oops(f"Every {format_duration(schedule.interval_seconds)}? Easy, tiger. Minimum is {format_duration(minimum)}.")
        return schedule

    def _nag(self, nag: str | None) -> int | None:
        if nag is None or nag.strip().lower() in OFF_WORDS:
            return None
        try:
            seconds = parse_duration(nag)
        except ParseError as exc:
            raise Oops(f"Nag: {exc}") from None
        minimum = self.bot.config.min_interval
        if seconds < minimum:
            raise Oops(f"Nagging every {format_duration(seconds)} would get me banned. Minimum is {format_duration(minimum)}.")
        return seconds

    def _when(self, when: str | None, tz: str) -> int | None:
        if when is None or not when.strip():
            return None
        try:
            dt = parse_when(when, get_zone(tz), datetime.now(timezone.utc))
        except ParseError as exc:
            raise Oops(str(exc)) from None
        return int(dt.timestamp())

    def _deliver(self, interaction: discord.Interaction, wanted: str | None) -> tuple[str, int | None, int | None, str | None]:
        """Figure out where reminders go. Returns (deliver, guild_id, channel_id, note for the user)."""
        if wanted != DELIVER_CHANNEL:
            return DELIVER_DM, None, None, None
        if interaction.guild is None:
            return DELIVER_DM, None, None, None  # we're already in DMs, "this channel" IS your DMs
        if not interaction.is_guild_integration():
            return DELIVER_DM, None, None, (
                "I'm not actually a member of this server (you're using me as a user app), "
                "so I can't post here. Sending to your DMs instead."
            )
        perms = interaction.app_permissions
        in_thread = isinstance(interaction.channel, discord.Thread)
        can_send = perms.send_messages_in_threads if in_thread else perms.send_messages
        if not (perms.view_channel and can_send and perms.embed_links):
            return DELIVER_DM, None, None, (
                "I don't have permission to post embeds in this channel, so these are going to your DMs. "
                "Give me View Channel + Send Messages + Embed Links here if you want them posted."
            )
        return DELIVER_CHANNEL, interaction.guild_id, interaction.channel_id, None

    def _load(self, interaction: discord.Interaction, task_id: int) -> Task:
        task = self.bot.store.get_for_user(task_id, interaction.user.id)
        if task is None:
            raise Oops(f"Can't find task #{task_id}. Pick one from the list when you type the `task` option.")
        return task

    async def _send(self, interaction: discord.Interaction, content: str | None = None, **kwargs) -> None:
        kwargs.setdefault("ephemeral", True)
        if interaction.response.is_done():
            await interaction.followup.send(content, **kwargs)
        else:
            await interaction.response.send_message(content, **kwargs)

    #endregion

    #region ADD

    @task.command(name="add", description="Add a task and tell me how often to bug you about it")
    @app_commands.describe(
        what="What do you need to do?",
        every="How often. 30m, 2h, 1d, weekdays, mon,wed,fri... leave empty for a one-time reminder",
        when="First reminder. 9am, in 20m, tomorrow 8am, friday 3pm... (required for one-time)",
        nag="Keep pinging every X until you hit Done. 10m, 30m... leave empty for no nagging",
        deliver="DM you (default) or post in this channel",
        notes="Extra details to show on the reminder",
    )
    @app_commands.choices(deliver=DELIVER_CHOICES)
    @app_commands.autocomplete(every=every_autocomplete, when=when_autocomplete, nag=nag_autocomplete)
    async def add(
        self,
        interaction: discord.Interaction,
        what: Range[str, 1, 200],
        every: Range[str, 1, 60] | None = None,
        when: Range[str, 1, 60] | None = None,
        nag: Range[str, 1, 30] | None = None,
        deliver: Choice[str] | None = None,
        notes: Range[str, 1, 1000] | None = None,
    ) -> None:
        bot = self.bot
        user_id = interaction.user.id
        now = engine.utcnow()

        if bot.store.count_open(user_id) >= bot.config.max_tasks_per_user:
            raise Oops(
                f"You've got {bot.config.max_tasks_per_user} open tasks already. "
                "Finish or remove some before piling on more."
            )

        tz = bot.user_tz(user_id)
        schedule = self._schedule(every)
        nag_seconds = self._nag(nag)

        if schedule.once and not when:
            raise Oops(
                "That's a one-time reminder, so I need a `when` (like `in 20m`, `5pm`, `tomorrow 9am`). "
                "Or give it an `every` to make it repeat."
            )
        when_ts = self._when(when, tz)
        try:
            first = engine.first_due(schedule, get_zone(tz), now, when_ts)
        except EngineError as exc:
            raise Oops(str(exc)) from None

        target, guild_id, channel_id, deliver_note = self._deliver(interaction, deliver.value if deliver else None)

        task = bot.store.add(
            Task(
                user_id=user_id,
                title=what.strip(),
                tz=tz,
                created_at=now,
                notes=notes.strip() if notes else None,
                interval_seconds=schedule.interval_seconds,
                weekdays=schedule.weekdays,
                next_due=first,
                nag_seconds=nag_seconds,
                deliver=target,
                guild_id=guild_id,
                channel_id=channel_id,
            ),
            now,
        )
        log.info("task #%s added by %s (%s)", task.id, user_id, render.schedule_text(task))

        tone = bot.user_tone(user_id)
        headline = [say(tone, "added")]
        if schedule.weekdays and not when:
            headline.append("No time given, so I went with 9am.")
        if deliver_note:
            headline.append(f"⚠️ {deliver_note}")
        if when and not bot.store.get_user(user_id)["tz"]:
            headline.append(f"*Reading times as **{tz}**. Wrong? Fix it with `/carzty timezone`.*")
        await self._send(interaction, embed=render.task_embed(task, "\n".join(headline)))

    #endregion

    #region LIST / SHOW

    @task.command(name="list", description="Everything you've got going on")
    @app_commands.describe(show_done="Include finished one-time tasks too")
    async def list_(self, interaction: discord.Interaction, show_done: bool = False) -> None:
        tasks = self.bot.store.list_for_user(interaction.user.id, include_done=show_done)
        tz = self.bot.user_tz(interaction.user.id)
        await self._send(interaction, embed=render.list_embed(tasks, tz, show_done))

    @task.command(name="show", description="All the details on one task")
    @app_commands.describe(task="Which one")
    @app_commands.autocomplete(task=any_task_autocomplete)
    async def show(self, interaction: discord.Interaction, task: int) -> None:
        t = self._load(interaction, task)
        kwargs = {"embed": render.task_embed(t)}
        if t.pending and t.state == ACTIVE:
            kwargs["view"] = reminder_view(t, self.bot.config.snooze_options)
        await self._send(interaction, **kwargs)

    #endregion

    #region DONE / SNOOZE / SKIP

    @task.command(name="done", description="Mark it done. If it isn't going off yet, it counts for the next one")
    @app_commands.describe(task="Which one")
    @app_commands.autocomplete(task=open_task_autocomplete)
    async def done(self, interaction: discord.Interaction, task: int) -> None:
        t = self._load(interaction, task)
        now = engine.utcnow()
        updated, outcome = engine.complete(t, now)
        self.bot.store.save(updated, now)

        tone = self.bot.user_tone(t.user_id)
        if outcome == "early":
            msg = f"✅ {say(tone, 'done_early')}\nNext reminder {render.ts(updated.next_due, 'R')}."
        else:
            key = "done_streak" if updated.streak >= 2 else "done"
            msg = f"✅ **{render.clip(t.title, 100)}** - {say(tone, key, streak=updated.streak)}"
            if outcome == "acked" and updated.next_due:
                msg += f"\nNext one {render.ts(updated.next_due, 'R')}."
        await self._send(interaction, msg)

    @task.command(name="snooze", description="Snooze a reminder that's going off right now")
    @app_commands.describe(task="Which one", duration="How long (15m, 1h) or until when (5pm, tomorrow 9am)")
    @app_commands.rename(duration="for")
    @app_commands.autocomplete(task=open_task_autocomplete, duration=snooze_autocomplete)
    async def snooze(self, interaction: discord.Interaction, task: int, duration: Range[str, 1, 60]) -> None:
        t = self._load(interaction, task)
        now = engine.utcnow()
        try:
            seconds = parse_duration(duration)
        except ParseError:
            until = self._when(duration, self.bot.user_tz(t.user_id))
            seconds = (until or now) - now
        updated = engine.snooze(t, now, seconds)
        self.bot.store.save(updated, now)
        tone = self.bot.user_tone(t.user_id)
        await self._send(interaction, f"💤 {say(tone, 'snoozed', until=render.ts(updated.followup_at, 't'))}")

    @task.command(name="skip", description="Skip the next occurrence (or dismiss the one going off)")
    @app_commands.describe(task="Which one")
    @app_commands.autocomplete(task=open_task_autocomplete)
    async def skip(self, interaction: discord.Interaction, task: int) -> None:
        t = self._load(interaction, task)
        now = engine.utcnow()
        updated, outcome = engine.skip(t, now)
        self.bot.store.save(updated, now)
        tone = self.bot.user_tone(t.user_id)
        msg = f"⏭️ {say(tone, 'dismissed' if outcome == 'dismissed' else 'skipped')}"
        if updated.recurring and updated.next_due:
            msg += f" Next one {render.ts(updated.next_due, 'R')}."
        await self._send(interaction, msg)

    #endregion

    #region PAUSE / RESUME / REMOVE

    @task.command(name="pause", description="Shut it up for a while without deleting it")
    @app_commands.describe(task="Which one")
    @app_commands.autocomplete(task=open_task_autocomplete)
    async def pause(self, interaction: discord.Interaction, task: int) -> None:
        t = self._load(interaction, task)
        updated = engine.pause(t)
        self.bot.store.save(updated, engine.utcnow())
        await self._send(interaction, f"⏸️ **{render.clip(t.title, 100)}** - {say(self.bot.user_tone(t.user_id), 'paused')}")

    @task.command(name="resume", description="Turn a paused task back on")
    @app_commands.describe(task="Which one")
    @app_commands.autocomplete(task=open_task_autocomplete)
    async def resume(self, interaction: discord.Interaction, task: int) -> None:
        t = self._load(interaction, task)
        now = engine.utcnow()
        updated = engine.resume(t, now)
        self.bot.store.save(updated, now)
        msg = f"▶️ **{render.clip(t.title, 100)}** - {say(self.bot.user_tone(t.user_id), 'resumed')}"
        if updated.next_due:
            msg += f" Next one {render.ts(updated.next_due, 'R')}."
        await self._send(interaction, msg)

    @task.command(name="remove", description="Delete a task for good")
    @app_commands.describe(task="Which one")
    @app_commands.autocomplete(task=any_task_autocomplete)
    async def remove(self, interaction: discord.Interaction, task: int) -> None:
        t = self._load(interaction, task)
        self.bot.store.delete(t.id, interaction.user.id)
        log.info("task #%s removed by %s", t.id, interaction.user.id)
        await self._send(interaction, f"🗑️ **{render.clip(t.title, 100)}** - {say(self.bot.user_tone(t.user_id), 'removed')}")

    #endregion

    #region EDIT

    @task.command(name="edit", description="Change a task. Only fill in what you want changed")
    @app_commands.describe(
        task="Which one",
        what="New name",
        every="New schedule. 30m, 1d, weekdays... or 'once' to make it one-time",
        when="New time for the next reminder",
        nag="Nag every X until Done, or 'off'",
        deliver="DM you or post in this channel",
        notes="New notes, or 'clear' to remove them",
    )
    @app_commands.choices(deliver=DELIVER_CHOICES)
    @app_commands.autocomplete(task=any_task_autocomplete, every=every_autocomplete, when=when_autocomplete, nag=nag_autocomplete)
    async def edit(
        self,
        interaction: discord.Interaction,
        task: int,
        what: Range[str, 1, 200] | None = None,
        every: Range[str, 1, 60] | None = None,
        when: Range[str, 1, 60] | None = None,
        nag: Range[str, 1, 30] | None = None,
        deliver: Choice[str] | None = None,
        notes: Range[str, 1, 1000] | None = None,
    ) -> None:
        t = self._load(interaction, task)
        if all(v is None for v in (what, every, when, nag, deliver, notes)):
            raise Oops("You didn't change anything. Bold strategy.")

        now = engine.utcnow()
        notes_out: list[str] = []

        if what:
            t = replace(t, title=what.strip())
        if notes is not None:
            t = replace(t, notes=None if notes.strip().lower() in CLEAR_WORDS else notes.strip())

        if every is not None or when is not None:
            schedule = self._schedule(every) if every is not None else Schedule(t.interval_seconds, t.weekdays)
            when_ts = self._when(when, t.tz)
            try:
                t = engine.reschedule(t, schedule, now, when_ts)
            except EngineError as exc:
                raise Oops(str(exc)) from None

        if nag is not None:
            t = engine.set_nag(t, self._nag(nag), now)

        if deliver is not None:
            target, guild_id, channel_id, deliver_note = self._deliver(interaction, deliver.value)
            t = replace(t, deliver=target, guild_id=guild_id, channel_id=channel_id, last_error=None)
            if deliver_note:
                notes_out.append(f"⚠️ {deliver_note}")

        self.bot.store.save(t, now)
        log.info("task #%s edited by %s", t.id, interaction.user.id)
        await self._send(interaction, embed=render.task_embed(t, "\n".join(["✏️ Updated.", *notes_out])))

    #endregion


async def setup(bot: CarztyBot) -> None:
    await bot.add_cog(TaskCommands(bot))
##xchronusx
