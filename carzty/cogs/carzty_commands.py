##xchronusx
"""
carzty.cogs.carzty_commands - the /carzty group. your personal settings + help.

Synopsis:
    /carzty timezone zone:<America/Phoenix>
    /carzty tone tone:<chill | salty | unhinged>
    /carzty me
    /carzty help

Description:
    Timezone only matters for reading what you TYPE ("9am" is 9am where?).
    Everything Carzty shows you uses Discord timestamps, which already render in
    your own local time.

Notes:
    Author: Zachary Wright (xchronusx)
    zoneinfo.available_timezones() is ~600 names. autocomplete caps at 25, so type a few letters.
"""

from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

import discord
from discord import app_commands
from discord.app_commands import Choice
from discord.ext import commands

from carzty import __version__
from carzty.config import TONES
from carzty.core import engine
from carzty.ui import render

if TYPE_CHECKING:
    from carzty.bot import CarztyBot

# the ones people actually pick, shown first when you haven't typed anything
POPULAR_ZONES = [
    "America/Phoenix", "America/Los_Angeles", "America/Denver", "America/Chicago", "America/New_York",
    "America/Anchorage", "Pacific/Honolulu", "America/Toronto", "America/Sao_Paulo", "Europe/London",
    "Europe/Berlin", "Europe/Paris", "Asia/Kolkata", "Asia/Tokyo", "Australia/Sydney", "UTC",
]

TONE_CHOICES = [
    Choice(name="chill - polite, grandma-safe", value="chill"),
    Choice(name="salty - sarcastic, mostly clean (default)", value="salty"),
    Choice(name="unhinged - swears at you. you asked for it", value="unhinged"),
]


@lru_cache(maxsize=1)
def _all_zones() -> list[str]:
    zones = sorted(z for z in available_timezones() if "/" in z or z == "UTC")
    # posix/ and right/ duplicates are clutter
    return [z for z in zones if not z.startswith(("posix/", "right/", "Etc/"))] + ["Etc/UTC"]


def _local_clock(tz: str) -> str:
    now = datetime.now(timezone.utc).astimezone(ZoneInfo(tz))
    return now.strftime("%I:%M %p").lstrip("0") + now.strftime(" on %a %b ") + str(now.day)


async def zone_autocomplete(interaction: discord.Interaction, current: str) -> list[Choice[str]]:  # noqa: ARG001
    current = (current or "").strip().lower().replace(" ", "_")
    if not current:
        return [Choice(name=z, value=z) for z in POPULAR_ZONES][:25]
    hits = [z for z in _all_zones() if current in z.lower()]
    hits.sort(key=lambda z: (not z.lower().split("/")[-1].startswith(current), len(z)))
    return [Choice(name=z, value=z) for z in hits[:25]]


class CarztyCommands(commands.Cog):
    """The /carzty group."""

    carzty = app_commands.Group(name="carzty", description="Your Carzty settings, and help")

    def __init__(self, bot: CarztyBot) -> None:
        self.bot = bot

    @carzty.command(name="timezone", description="Set your timezone so '9am' means YOUR 9am")
    @app_commands.describe(zone="Start typing a city, like Phoenix or London")
    @app_commands.autocomplete(zone=zone_autocomplete)
    async def timezone_(self, interaction: discord.Interaction, zone: app_commands.Range[str, 1, 64]) -> None:
        zone = zone.strip()
        try:
            ZoneInfo(zone)
        except (ZoneInfoNotFoundError, ValueError):
            await interaction.response.send_message(
                f"❌ `{zone}` isn't a timezone I know. Pick one from the list, like `America/Phoenix`.", ephemeral=True
            )
            return
        self.bot.store.set_user(interaction.user.id, engine.utcnow(), tz=zone)
        await interaction.response.send_message(
            f"🕒 Timezone set to **{zone}**. It's {_local_clock(zone)} there.\n"
            "-# New tasks use this. Existing ones keep the times they already have. Use `/task edit` with a new `when` if you moved.",
            ephemeral=True,
        )

    @carzty.command(name="tone", description="How mean should I be?")
    @app_commands.describe(tone="Pick your poison")
    @app_commands.choices(tone=TONE_CHOICES)
    async def tone(self, interaction: discord.Interaction, tone: Choice[str]) -> None:
        if tone.value not in TONES:
            await interaction.response.send_message("❌ Not a tone.", ephemeral=True)
            return
        self.bot.store.set_user(interaction.user.id, engine.utcnow(), tone=tone.value)
        blurbs = {
            "chill": "Chill mode. I'll be nice. Promise.",
            "salty": "Salty it is. Good choice.",
            "unhinged": "Unhinged mode. Oh, you're gonna regret this. 😈",
        }
        await interaction.response.send_message(blurbs[tone.value], ephemeral=True)

    @carzty.command(name="me", description="Your settings and how you're doing")
    async def me(self, interaction: discord.Interaction) -> None:
        user_id = interaction.user.id
        saved = self.bot.store.get_user(user_id)
        tz = self.bot.user_tz(user_id)
        tone = self.bot.user_tone(user_id)
        tasks = self.bot.store.list_for_user(user_id, include_done=True, limit=1000)
        open_tasks = [t for t in tasks if t.state != "done"]
        ringing = [t for t in open_tasks if t.pending]
        best = max((t.streak for t in tasks), default=0)
        done_total = sum(t.times_done for t in tasks)

        embed = discord.Embed(title=f"{interaction.user.display_name}'s Carzty", color=render.COLOR_INFO)
        embed.add_field(
            name="Timezone",
            value=f"{tz}{'' if saved['tz'] else ' (default)'}\n{_local_clock(tz)}",
            inline=True,
        )
        embed.add_field(name="Tone", value=f"{tone}{'' if saved['tone'] else ' (default)'}", inline=True)
        embed.add_field(name="Open tasks", value=f"{len(open_tasks)} / {self.bot.config.max_tasks_per_user}", inline=True)
        embed.add_field(name="Waiting on you", value=str(len(ringing)), inline=True)
        embed.add_field(name="Times you hit Done", value=str(done_total), inline=True)
        embed.add_field(name="Best streak", value=f"🔥 {best}" if best else "-", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @carzty.command(name="help", description="How to use Carzty")
    async def help_(self, interaction: discord.Interaction) -> None:
        user_id = interaction.user.id
        embed = render.help_embed(self.bot.user_tz(user_id), self.bot.user_tone(user_id))
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @carzty.command(name="about", description="Version, uptime and where the code lives")
    async def about(self, interaction: discord.Interaction) -> None:
        stats = self.bot.store.stats()
        embed = discord.Embed(
            title=f"Carzty v{__version__}",
            description="A Discord bot that nags you until you do the thing.\n"
            "Open source: https://github.com/xchronusx/carzty",
            color=render.COLOR_INFO,
        )
        embed.add_field(name="Up since", value=render.ts(self.bot.started_at, "R"), inline=True)
        embed.add_field(name="Tasks tracked", value=str(stats["total"]), inline=True)
        embed.add_field(name="People", value=str(stats["users"]), inline=True)
        embed.add_field(name="Latency", value=f"{self.bot.latency * 1000:.0f} ms", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: CarztyBot) -> None:
    await bot.add_cog(CarztyCommands(bot))
##xchronusx
