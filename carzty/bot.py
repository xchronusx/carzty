##xchronusx
"""
carzty.bot - wires it all together.

Synopsis:
    bot = CarztyBot(config, store)
    await bot.start(config.token)

Description:
    * loads the two cogs (/task and /carzty)
    * registers the persistent Done/Snooze/Skip buttons
    * syncs slash commands with Discord, but only when they actually changed
      (we hash the command payload and keep the hash in sqlite, so restarting
      the bot 40 times while debugging doesn't get you rate limited)
    * kicks off the reminder loop

    Works as a server bot AND a user-installed app. User install means you can
    use /task in any server or DM, even ones Carzty isn't a member of. It'll
    just DM you the reminders in that case.

Notes:
    Author: Zachary Wright (xchronusx)
    No privileged intents needed. No message content. It only reads slash commands.
"""

from __future__ import annotations

import hashlib
import json
import logging

import discord
from discord import app_commands
from discord.ext import commands

from carzty import __version__
from carzty.config import TONES, Config
from carzty.core import engine
from carzty.core.store import Store
from carzty.errors import USER_ERRORS
from carzty.scheduler import Scheduler
from carzty.ui.buttons import DYNAMIC_ITEMS

log = logging.getLogger("carzty.bot")

COGS = ("carzty.cogs.task_commands", "carzty.cogs.carzty_commands")


class CarztyTree(app_commands.CommandTree):
    """Command tree with an allowlist and an error handler that doesn't leave people hanging."""

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        allowed = getattr(self.client, "config", None) and self.client.config.allowed_user_ids
        if allowed and interaction.user.id not in allowed:
            await interaction.response.send_message(
                "This Carzty is private. Run your own, it's free: https://github.com/xchronusx/carzty",
                ephemeral=True,
            )
            return False
        return True

    async def on_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        if isinstance(error, app_commands.CheckFailure):
            return  # interaction_check already answered
        original = getattr(error, "original", error)
        if isinstance(original, USER_ERRORS):
            msg = f"❌ {original}"  # their mistake (or ours, politely). no stack trace needed
        else:
            name = interaction.command.qualified_name if interaction.command else "?"
            log.error("/%s blew up for %s", name, interaction.user.id, exc_info=original)
            msg = "💥 Something broke on my end. It's in the logs. Try again, and if it keeps happening, open an issue."
        try:
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        except discord.HTTPException:
            pass


class CarztyBot(commands.Bot):
    def __init__(self, config: Config, store: Store, force_sync: bool = False) -> None:
        intents = discord.Intents.none()
        intents.guilds = True  # channel cache so we can find where to post. that's it.
        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=intents,
            help_command=None,
            tree_cls=CarztyTree,
            allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=True),
            allowed_installs=app_commands.AppInstallationType(guild=True, user=True),
            allowed_contexts=app_commands.AppCommandContext(guild=True, dm_channel=True, private_channel=True),
            activity=discord.CustomActivity(name="judging your to-do list"),
        )
        self.config = config
        self.store = store
        self.force_sync = force_sync
        self.scheduler = Scheduler(self)
        self.started_at = engine.utcnow()

    #region USER PREFS

    def user_tz(self, user_id: int) -> str:
        return self.store.get_user(user_id)["tz"] or self.config.default_tz

    def user_tone(self, user_id: int) -> str:
        tone = self.store.get_user(user_id)["tone"]
        return tone if tone in TONES else self.config.default_tone

    #endregion

    #region STARTUP

    async def setup_hook(self) -> None:
        for cog in COGS:
            await self.load_extension(cog)
        self.add_dynamic_items(*DYNAMIC_ITEMS)
        await self.sync_commands(force=self.force_sync)
        self.scheduler.start()

    def command_payload(self) -> list[dict]:
        return [cmd.to_dict(self.tree) for cmd in self.tree.get_commands()]

    async def sync_commands(self, force: bool = False) -> bool:
        """Push slash commands to Discord if they changed since last time. Returns True if it synced."""
        payload = json.dumps(self.command_payload(), sort_keys=True, default=str)
        digest = hashlib.sha256(payload.encode()).hexdigest()
        if not force and self.store.get_meta("command_hash") == digest:
            log.info("slash commands unchanged, skipping sync")
            return False
        try:
            synced = await self.tree.sync()
        except discord.HTTPException as exc:
            # don't die over this. reminders still work with whatever commands Discord already has,
            # and since we didn't save the hash it'll try again next startup
            log.error("slash command sync failed (%s %s). carrying on with the old ones", exc.status, exc.text)
            return False
        self.store.set_meta("command_hash", digest)
        log.info("synced %s slash command group(s) with Discord", len(synced))
        return True

    async def on_ready(self) -> None:
        log.info("==== CARZTY v%s ONLINE as %s (%s) in %s server(s) ====", __version__, self.user, self.user.id, len(self.guilds))
        if self.user and not getattr(self, "_invite_logged", False):
            self._invite_logged = True
            perms = discord.Permissions(view_channel=True, send_messages=True, send_messages_in_threads=True, embed_links=True)
            url = discord.utils.oauth_url(self.user.id, permissions=perms, scopes=("bot", "applications.commands"))
            log.info("invite link: %s", url)

    async def close(self) -> None:
        log.info("shutting down, see ya")
        await self.scheduler.stop()
        await super().close()
        self.store.close()

    #endregion
##xchronusx
