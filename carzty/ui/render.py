##xchronusx
"""
carzty.ui.render - makes the embeds look like somebody cared.

Synopsis:
    reminder_embed(task, fired, tone, now)
    task_embed(task)
    list_embed(tasks, tz_name, show_done)

Description:
    All the times use Discord's <t:...> timestamp markup, which renders in
    whatever timezone the person LOOKING at it is in. So the bot never has to
    guess your timezone just to show you a time. Only typing times needs it.

Notes:
    Author: Zachary Wright (xchronusx)
    Discord limits: title 256, description 4096, field value 1024, 25 fields. Don't poke the bear.
"""

from __future__ import annotations

import discord

from carzty import __version__
from carzty.core.engine import Fired
from carzty.core.models import DELIVER_CHANNEL, DONE, PAUSED, Task
from carzty.core.timeparse import DAY, describe_schedule, format_duration
from carzty.voice import say

COLOR_SCHEDULED = discord.Color.from_rgb(88, 101, 242)  # blurple
COLOR_SNOOZE = discord.Color.from_rgb(155, 89, 182)
COLOR_NAG_SOFT = discord.Color.from_rgb(241, 196, 15)
COLOR_NAG_MID = discord.Color.from_rgb(230, 126, 34)
COLOR_NAG_HOT = discord.Color.from_rgb(231, 76, 60)
COLOR_DONE = discord.Color.from_rgb(46, 204, 113)
COLOR_INFO = discord.Color.from_rgb(52, 152, 219)
COLOR_MUTED = discord.Color.from_rgb(127, 140, 141)

LATE_THRESHOLD = 120  # seconds behind before we admit we were asleep


def ts(epoch: int | None, style: str = "f") -> str:
    return f"<t:{int(epoch)}:{style}>" if epoch else "-"


def clip(text: str | None, limit: int) -> str:
    text = text or ""
    return text if len(text) <= limit else text[: limit - 1] + "…"


#region TEXT BITS

def schedule_text(task: Task) -> str:
    base = describe_schedule(task.interval_seconds, task.weekdays)
    if not task.recurring:
        return "one time"
    # daily-ish schedules get "at <time>" because that's the part you actually care about
    daily_ish = bool(task.weekdays) or (task.interval_seconds or 0) % DAY == 0
    if daily_ish and task.next_due:
        return f"{base} at {ts(task.next_due, 't')}"
    return base


def status_text(task: Task) -> str:
    if task.state == DONE:
        return f"✅ done {ts(task.last_done_at, 'R')}" if task.last_done_at else "✅ done"
    if task.state == PAUSED:
        return "⏸️ paused"
    if task.pending:
        bits = ["🔔 waiting on you"]
        if task.followup_kind == "snooze" and task.followup_at:
            bits.append(f"snoozed until {ts(task.followup_at, 't')}")
        elif task.followup_at:
            bits.append(f"next nag {ts(task.followup_at, 'R')}")
        return " · ".join(bits)
    if task.next_due:
        return f"⏰ next {ts(task.next_due, 'R')}"
    return "💤 nothing scheduled"


def delivery_text(task: Task) -> str:
    if task.deliver == DELIVER_CHANNEL and task.channel_id:
        return f"<#{task.channel_id}>"
    return "your DMs"


def task_line(task: Task) -> str:
    """One entry in /task list."""
    head = f"**#{task.id}** {clip(task.title, 80)}"
    meta = [status_text(task)]
    if task.recurring:
        meta.append(schedule_text(task))
    elif task.next_due and not task.pending and task.state != DONE:
        meta.append(ts(task.next_due, "f"))
    if task.nag_seconds:
        meta.append(f"nags every {format_duration(task.nag_seconds)}")
    if task.streak >= 2:
        meta.append(f"🔥 {task.streak}")
    if task.last_error:
        meta.append("⚠️")
    return f"{head}\n↳ {' · '.join(meta)}"

#endregion


#region EMBEDS

def reminder_embed(task: Task, fired: Fired, tone: str, now: int) -> discord.Embed:
    if fired.kind == "snooze":
        color, key = COLOR_SNOOZE, "snooze_over"
    elif fired.kind == "nag":
        color = COLOR_NAG_SOFT if fired.nag_number <= 2 else COLOR_NAG_MID if fired.nag_number <= 5 else COLOR_NAG_HOT
        key = "nag"
    else:
        color, key = COLOR_SCHEDULED, "scheduled"

    lines = [say(tone, key, nag=fired.nag_number, title=task.title)]
    if fired.kind == "scheduled" and fired.late_by > LATE_THRESHOLD:
        lines.append(say(tone, "late", due=ts(now - fired.late_by, "R")))
    if fired.missed_previous:
        lines.append(say(tone, "missed"))
    if fired.gave_up and task.nag_seconds:
        lines.append(f"*{say(tone, 'gave_up')}*")
    if task.notes:
        lines.append("")
        lines.extend(f"> {ln}" for ln in clip(task.notes, 1000).splitlines())

    embed = discord.Embed(
        title=clip(("🔔 " if fired.kind == "scheduled" else "⏰ ") + task.title, 256),
        description=clip("\n".join(lines), 4096),
        color=color,
    )
    if task.recurring:
        embed.add_field(name="Schedule", value=schedule_text(task), inline=True)
        if task.next_due:
            embed.add_field(name="Next one", value=ts(task.next_due, "R"), inline=True)
    if task.nag_seconds and task.followup_at:
        embed.add_field(name="Next nag", value=ts(task.followup_at, "R"), inline=True)
    if task.streak >= 2:
        embed.add_field(name="Streak", value=f"🔥 {task.streak}", inline=True)
    embed.set_footer(text=f"Task #{task.id} · Carzty")
    return embed


def task_embed(task: Task, headline: str | None = None) -> discord.Embed:
    color = COLOR_DONE if task.state == DONE else COLOR_MUTED if task.state == PAUSED else COLOR_INFO
    desc = []
    if headline:
        desc.append(headline)
    if task.notes:
        if desc:
            desc.append("")
        desc.extend(f"> {ln}" for ln in clip(task.notes, 1000).splitlines())

    embed = discord.Embed(title=clip(task.title, 256), description=clip("\n".join(desc), 4096) or None, color=color)
    embed.add_field(name="Status", value=status_text(task), inline=False)
    embed.add_field(name="Schedule", value=schedule_text(task), inline=True)
    if task.next_due and task.state != DONE:
        embed.add_field(name="Next reminder", value=f"{ts(task.next_due, 'f')}\n{ts(task.next_due, 'R')}", inline=True)
    embed.add_field(
        name="Nagging",
        value=f"every {format_duration(task.nag_seconds)}" if task.nag_seconds else "off",
        inline=True,
    )
    embed.add_field(name="Goes to", value=delivery_text(task), inline=True)
    if task.times_fired or task.times_done:
        stats = f"done {task.times_done}x"
        if task.streak:
            stats += f" · 🔥 {task.streak} streak"
        embed.add_field(name="Stats", value=stats, inline=True)
    if task.last_error:
        embed.add_field(name="⚠️ Last problem", value=clip(task.last_error, 1024), inline=False)
    embed.set_footer(text=f"Task #{task.id} · timezone {task.tz}")
    return embed


def list_embed(tasks: list[Task], tz_name: str, show_done: bool) -> discord.Embed:
    title = "Your tasks" if not show_done else "Your tasks (including finished ones)"
    if not tasks:
        embed = discord.Embed(
            title=title,
            description="Nothing. Either you're on top of your life or you haven't added anything yet.\n"
            "Try `/task add what:Stretch every:1h`",
            color=COLOR_MUTED,
        )
        return embed

    chunks: list[str] = []
    used = 0
    shown = 0
    for task in tasks:
        line = task_line(task)
        if used + len(line) + 2 > 3900:
            break
        chunks.append(line)
        used += len(line) + 2
        shown += 1
    if shown < len(tasks):
        chunks.append(f"\n…and {len(tasks) - shown} more. Finish some stuff.")

    embed = discord.Embed(title=f"{title} ({len(tasks)})", description="\n\n".join(chunks), color=COLOR_INFO)
    embed.set_footer(text=f"Times show in your local time. Typed times use {tz_name}.")
    return embed


def stamp(embed: discord.Embed | None, text: str, color: discord.Color | None = None) -> discord.Embed:
    """Slap a status line on an existing reminder embed after somebody clicks a button."""
    embed = discord.Embed.from_dict(embed.to_dict()) if embed else discord.Embed()
    for i, f in enumerate(embed.fields):
        if f.name == "Status":
            embed.remove_field(i)
            break
    # nag/next fields are stale once you've clicked something
    for name in ("Next nag",):
        for i, f in enumerate(embed.fields):
            if f.name == name:
                embed.remove_field(i)
                break
    embed.add_field(name="Status", value=clip(text, 1024), inline=False)
    if color is not None:
        embed.color = color
    return embed


def help_embed(tz_name: str, tone: str) -> discord.Embed:
    e = discord.Embed(
        title="Carzty - the bot that nags you until you do the thing",
        color=COLOR_INFO,
        description=(
            "**Add stuff**\n"
            "`/task add what:Stretch every:1h` - every hour, starting an hour from now\n"
            "`/task add what:Meds every:1d when:9am nag:10m` - daily at 9, nags every 10m until you hit Done\n"
            "`/task add what:Standup notes every:weekdays when:8:45am`\n"
            "`/task add what:Trash every:mon,thu when:7pm deliver:Post here`\n"
            "`/task add what:Call the dentist when:tomorrow 10am` - one time\n\n"
            "**Manage it**\n"
            "`/task list` · `/task show` · `/task done` · `/task snooze` · `/task skip`\n"
            "`/task pause` · `/task resume` · `/task edit` · `/task remove`\n\n"
            "**`every`** → `30m` `2h` `1d` `1w` `1h30m` `hourly` `daily` `weekdays` `weekends` `mon,wed,fri` `tue-thu`\n"
            "**`when`** → `now` `in 20m` `9am` `21:00` `noon` `tonight` `tomorrow 8am` `friday 3pm` "
            "`next monday` `10/25 2pm` `oct 25` `2026-10-25 14:00`\n"
            "**`nag`** → keep pinging every X until you hit ✅ Done\n\n"
            "**You**\n"
            f"`/carzty timezone` (yours: **{tz_name}**) · `/carzty tone` (yours: **{tone}**) · `/carzty me`"
        ),
    )
    e.set_footer(text=f"Carzty v{__version__} · github.com/xchronusx/carzty")
    return e

#endregion
##xchronusx
