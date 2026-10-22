##xchronusx
"""
carzty.scheduler - the loop that actually yells at people.

Synopsis:
    scheduler = Scheduler(bot)
    scheduler.start()      # in setup_hook
    await scheduler.tick() # one pass, handy for tests

Description:
    Every TICK_SECONDS: grab everything that's due, run it through the engine,
    send the reminder, save. One task blowing up never takes down the loop.

    Where reminders go:
      1. the channel you picked with deliver:"Post in this channel"
      2. your DMs, if the channel's gone or I lost permission there
      3. nowhere, if your DMs are closed too. that gets written to last_error
         and shows up as a ⚠️ in /task list so you know why it's quiet.

    Order of operations is send-then-save on purpose. If the bot dies mid-tick
    you might get a duplicate reminder. The alternative is a lost one, and a
    reminder bot that loses reminders is just a very expensive nothing.

Notes:
    Author: Zachary Wright (xchronusx)
    Once an hour it also bins finished tasks older than PURGE_DONE_AFTER_DAYS. 0 turns that off.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from typing import TYPE_CHECKING

import discord

from carzty.core import engine
from carzty.core.engine import Fired
from carzty.core.models import DELIVER_CHANNEL, Task
from carzty.ui import render
from carzty.ui.buttons import reminder_view

if TYPE_CHECKING:
    from carzty.bot import CarztyBot

log = logging.getLogger("carzty.scheduler")

HOUSEKEEPING_EVERY = 3600


class Scheduler:
    def __init__(self, bot: CarztyBot) -> None:
        self.bot = bot
        self._runner: asyncio.Task | None = None
        self._last_housekeeping = 0
        self.ticks = 0

    #region LIFECYCLE

    def start(self) -> None:
        if self._runner is None or self._runner.done():
            self._runner = asyncio.create_task(self._run(), name="carzty-scheduler")

    async def stop(self) -> None:
        if self._runner and not self._runner.done():
            self._runner.cancel()
            try:
                await self._runner
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        await self.bot.wait_until_ready()
        log.info("scheduler up, ticking every %ss", self.bot.config.tick_seconds)
        while not self.bot.is_closed():
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - the loop does not die. ever.
                log.exception("tick blew up, going again next round")
            await asyncio.sleep(self.bot.config.tick_seconds)

    #endregion

    #region THE TICK

    async def tick(self) -> int:
        """One pass. Returns how many reminders went out."""
        self.ticks += 1
        now = engine.utcnow()
        sent = 0
        for task in self.bot.store.due(now):
            try:
                updated, fired = engine.process(task, now, self.bot.config.max_nags)
                if fired is not None:
                    updated = await self.deliver(updated, fired, now)
                    sent += 1
                self.bot.store.save(updated, now)
            except Exception:  # noqa: BLE001
                log.exception("task #%s failed during tick", task.id)

        if now - self._last_housekeeping >= HOUSEKEEPING_EVERY:
            self._last_housekeeping = now
            self.housekeeping(now)
        return sent

    def housekeeping(self, now: int) -> None:
        days = self.bot.config.purge_done_after_days
        if days <= 0:
            return
        purged = self.bot.store.purge_done(now - days * 86400)
        if purged:
            log.info("housekeeping: binned %s finished task(s) older than %s days", purged, days)

    #endregion

    #region DELIVERY

    async def _resolve_channel(self, channel_id: int) -> discord.abc.Messageable | None:
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except (discord.NotFound, discord.Forbidden):
                return None
        return channel if isinstance(channel, discord.abc.Messageable) else None

    async def _resolve_user(self, user_id: int) -> discord.User | None:
        user = self.bot.get_user(user_id)
        if user is None:
            try:
                user = await self.bot.fetch_user(user_id)
            except discord.NotFound:
                return None
        return user

    async def deliver(self, task: Task, fired: Fired, now: int) -> Task:
        tone = self.bot.user_tone(task.user_id)
        embed = render.reminder_embed(task, fired, tone, now)
        view = reminder_view(task, self.bot.config.snooze_options)
        mentions = discord.AllowedMentions(users=[discord.Object(task.user_id)], everyone=False, roles=False)

        message: discord.Message | None = None
        problem: str | None = None

        if task.deliver == DELIVER_CHANNEL and task.channel_id:
            channel = await self._resolve_channel(task.channel_id)
            if channel is None:
                problem = f"Couldn't find channel <#{task.channel_id}> anymore, so I DM'd you instead."
            else:
                try:
                    message = await channel.send(
                        content=f"<@{task.user_id}>", embed=embed, view=view, allowed_mentions=mentions
                    )
                except discord.Forbidden:
                    problem = f"Lost permission to post in <#{task.channel_id}>, so I DM'd you instead."
                except discord.HTTPException as exc:
                    problem = f"Discord choked posting in <#{task.channel_id}> ({exc.status}), so I DM'd you instead."

        if message is None:
            user = await self._resolve_user(task.user_id)
            if user is None:
                problem = "Couldn't look you up on Discord at all. Weird."
            else:
                try:
                    message = await user.send(embed=embed, view=view)
                except discord.Forbidden:
                    problem = (
                        "Couldn't DM you. Your DMs are closed to me, or we don't share a server. "
                        "Open your DMs or switch this task to deliver:'Post in this channel'."
                    )
                except discord.HTTPException as exc:
                    problem = f"Discord choked sending your DM ({exc.status})."

        if message is not None:
            log.info(
                "sent %s reminder for task #%s to %s (%s)",
                fired.kind, task.id, task.user_id, "channel" if message.guild else "dm",
            )
            return replace(
                task,
                last_message_id=message.id,
                last_message_channel_id=message.channel.id,
                last_error=problem,  # fallback note, or None if it all went fine
            )

        log.warning("could not deliver task #%s to %s: %s", task.id, task.user_id, problem)
        return replace(task, last_error=problem)

    #endregion
##xchronusx
