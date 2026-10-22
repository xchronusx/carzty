##xchronusx
"""
carzty.ui.buttons - the Done / Snooze / Skip buttons on every reminder.

Synopsis:
    view = reminder_view(task, snooze_options=(900, 3600))
    bot.add_dynamic_items(DoneButton, SnoozeButton, SkipButton)

Description:
    These are DynamicItems, which means the task id rides inside the button's
    custom_id. Restart the bot, update it, whatever - buttons on old messages
    still work because there's no in-memory view to lose.

    Only the person who owns the task can press them. Everybody else gets told
    to mind their own business.

Notes:
    Author: Zachary Wright (xchronusx)
    custom_id format: carzty:<action>:<task id>[:<seconds>]   (100 char limit, we're nowhere near it)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord

from carzty.core import engine
from carzty.core.engine import EngineError
from carzty.core.models import Task
from carzty.core.timeparse import format_duration
from carzty.ui import render
from carzty.voice import say

if TYPE_CHECKING:
    from carzty.bot import CarztyBot

log = logging.getLogger("carzty.buttons")


#region SHARED

async def _load(interaction: discord.Interaction, task_id: int) -> Task | None:
    bot: CarztyBot = interaction.client  # type: ignore[assignment]
    task = bot.store.get(task_id)
    if task is None:
        # task got removed, so these buttons are just decoration now. kill 'em.
        await interaction.response.edit_message(view=None)
        await interaction.followup.send("That task doesn't exist anymore.", ephemeral=True)
        return None
    if interaction.user.id != task.user_id:
        tone = bot.user_tone(interaction.user.id)
        await interaction.response.send_message(say(tone, "not_yours"), ephemeral=True)
        return None
    return task


async def _already_handled(interaction: discord.Interaction, why: str) -> None:
    await interaction.response.edit_message(view=None)
    await interaction.followup.send(why, ephemeral=True)


def _first_embed(interaction: discord.Interaction) -> discord.Embed | None:
    msg = interaction.message
    return msg.embeds[0] if msg and msg.embeds else None

#endregion


#region BUTTONS

class DoneButton(discord.ui.DynamicItem[discord.ui.Button], template=r"carzty:done:(?P<id>[0-9]+)"):
    def __init__(self, task_id: int) -> None:
        self.task_id = task_id
        super().__init__(
            discord.ui.Button(
                label="Done",
                emoji="✅",
                style=discord.ButtonStyle.success,
                custom_id=f"carzty:done:{task_id}",
            )
        )

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match):  # noqa: ARG003
        return cls(int(match["id"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        bot: CarztyBot = interaction.client  # type: ignore[assignment]
        task = await _load(interaction, self.task_id)
        if task is None:
            return
        if not task.pending:
            await _already_handled(interaction, "Already handled. Nothing's going off for that one right now.")
            return

        now = engine.utcnow()
        try:
            updated, _outcome = engine.complete(task, now)
        except EngineError as exc:
            await _already_handled(interaction, str(exc))
            return
        bot.store.save(updated, now)

        tone = bot.user_tone(task.user_id)
        line = say(tone, "done_streak" if updated.streak >= 2 else "done", streak=updated.streak)
        status = f"✅ Done {render.ts(now, 'R')}. {line}"
        if updated.recurring and updated.next_due:
            status += f"\nNext one {render.ts(updated.next_due, 'R')}."
        embed = render.stamp(_first_embed(interaction), status, render.COLOR_DONE)
        await interaction.response.edit_message(embed=embed, view=None)
        log.info("task #%s done via button by %s", task.id, interaction.user.id)


class SnoozeButton(discord.ui.DynamicItem[discord.ui.Button], template=r"carzty:snooze:(?P<id>[0-9]+):(?P<secs>[0-9]+)"):
    def __init__(self, task_id: int, seconds: int) -> None:
        self.task_id = task_id
        self.seconds = seconds
        super().__init__(
            discord.ui.Button(
                label=format_duration(seconds),
                emoji="💤",
                style=discord.ButtonStyle.secondary,
                custom_id=f"carzty:snooze:{task_id}:{seconds}",
            )
        )

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match):  # noqa: ARG003
        return cls(int(match["id"]), int(match["secs"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        bot: CarztyBot = interaction.client  # type: ignore[assignment]
        task = await _load(interaction, self.task_id)
        if task is None:
            return

        now = engine.utcnow()
        try:
            updated = engine.snooze(task, now, self.seconds)
        except EngineError as exc:
            await _already_handled(interaction, str(exc))
            return
        bot.store.save(updated, now)

        tone = bot.user_tone(task.user_id)
        line = say(tone, "snoozed", until=render.ts(updated.followup_at, "t"))
        embed = render.stamp(_first_embed(interaction), f"💤 {line}", render.COLOR_SNOOZE)
        await interaction.response.edit_message(embed=embed, view=None)
        log.info("task #%s snoozed %ss by %s", task.id, self.seconds, interaction.user.id)


class SkipButton(discord.ui.DynamicItem[discord.ui.Button], template=r"carzty:skip:(?P<id>[0-9]+)"):
    def __init__(self, task_id: int) -> None:
        self.task_id = task_id
        super().__init__(
            discord.ui.Button(
                label="Skip",
                emoji="⏭️",
                style=discord.ButtonStyle.secondary,
                custom_id=f"carzty:skip:{task_id}",
            )
        )

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match):  # noqa: ARG003
        return cls(int(match["id"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        bot: CarztyBot = interaction.client  # type: ignore[assignment]
        task = await _load(interaction, self.task_id)
        if task is None:
            return
        if not task.pending:
            await _already_handled(interaction, "Already handled. Use `/task skip` if you want to skip the next one.")
            return

        now = engine.utcnow()
        try:
            updated, _outcome = engine.skip(task, now)
        except EngineError as exc:
            await _already_handled(interaction, str(exc))
            return
        bot.store.save(updated, now)

        tone = bot.user_tone(task.user_id)
        status = f"⏭️ {say(tone, 'dismissed')}"
        if updated.recurring and updated.next_due:
            status += f" Next one {render.ts(updated.next_due, 'R')}."
        embed = render.stamp(_first_embed(interaction), status, render.COLOR_MUTED)
        await interaction.response.edit_message(embed=embed, view=None)
        log.info("task #%s skipped via button by %s", task.id, interaction.user.id)

#endregion


def reminder_view(task: Task, snooze_options: tuple[int, ...]) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(DoneButton(task.id))
    for secs in snooze_options[:3]:
        view.add_item(SnoozeButton(task.id, secs))
    if task.recurring:
        view.add_item(SkipButton(task.id))
    return view


DYNAMIC_ITEMS = (DoneButton, SnoozeButton, SkipButton)
##xchronusx
