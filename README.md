# Carzty

**A Discord bot that reminds you to do stuff, then keeps reminding you until you actually do it.**

[![ci](https://github.com/xchronusx/carzty/actions/workflows/ci.yml/badge.svg)](https://github.com/xchronusx/carzty/actions/workflows/ci.yml)
![python](https://img.shields.io/badge/python-3.10%2B-blue)
![license](https://img.shields.io/badge/license-MIT-green)

```
/task add what:Take meds every:1d when:9am nag:10m
```

At 9am Carzty DMs you. If you don't hit **Done**, it pings you again every 10 minutes and gets
more disappointed in you each time. Tomorrow at 9 it starts over. That's the whole idea.

Most reminder apps let you swipe the notification away and forget about it. This one won't let you
off that easy.

---

## What it does

- **Recurring reminders.** `30m`, `2h`, `1d`, `1w`, `weekdays`, `weekends`, `mon,wed,fri`, `tue-thu`, `every other day`...
- **One-time reminders.** `in 20m`, `5pm`, `tomorrow 9am`, `friday 3pm`, `oct 25`, `2026-12-01 14:00`
- **Nag mode.** Keeps pinging every X until you hit Done. Gives up after 24 nags by default, because there are limits. Barely.
- **Buttons on every reminder.** ✅ Done, 💤 Snooze (15m / 1h, configurable), ⏭️ Skip. They keep working after the bot restarts.
- **DM or channel.** Reminders go to your DMs by default, or post them in a channel so the whole server can watch you fail.
- **Timezones that work.** Every user sets their own. Daily reminders stay at 9am through daylight saving changes.
  Every time it shows you uses Discord timestamps, so they display in *your* local time automatically.
- **Three tones.** `chill` (polite), `salty` (default, sarcastic), `unhinged` (swears at you, opt-in only).
- **Server bot or user app.** Invite it to a server, or install it to your account and use `/task` from any server or DM.
- **Survives downtime.** If the bot was off for 6 hours, you get *one* "hey I was napping" reminder, not 36 of them.
- **Streaks.** Hit Done on time and it counts. Miss one and the streak resets. 🔥
- **Self-hosted, no cloud anything.** One SQLite file. Runs fine on a Raspberry Pi, a Proxmox LXC, or the PC under your desk.

## Install

**Step 0:** make a bot in the Discord developer portal and grab its token. About 3 minutes:
[docs/discord-setup.md](docs/discord-setup.md).

Then pick one. Every option ends in the same setup wizard: paste your token (it gets checked with Discord),
confirm the timezone it detected, pick a tone, and it hands you the invite link.

### Windows - one line

Open PowerShell and paste:

```powershell
irm https://raw.githubusercontent.com/xchronusx/carzty/main/scripts/windows/carzty.install.zw.ps1 | iex
```

That downloads Carzty to `%USERPROFILE%\Carzty`, installs Python for you (winget, no admin) if you don't
have it, runs the wizard, and asks if you want it to start with Windows. Run the same line again later to update.

Rather click things? Download the ZIP from GitHub (green **Code** button → **Download ZIP**), unzip it,
double-click **`install.cmd`**. After that, **`start.cmd`** runs it.

### Linux / macOS - one line

```bash
curl -fsSL https://raw.githubusercontent.com/xchronusx/carzty/main/scripts/linux/carzty.install.zw.sh | bash
```

Installs to `~/carzty`, builds a venv, runs the wizard. On Linux it offers to set itself up as a systemd
user service, so it runs in the background and comes back after a reboot. No root needed.
Needs Python 3.10+ (`sudo apt install python3 python3-venv` on Debian/Ubuntu, `brew install python` on a Mac).

### Docker - two lines

```bash
docker run --rm -it -v carzty-data:/app/data ghcr.io/xchronusx/carzty setup
docker run -d --name carzty --restart unless-stopped -v carzty-data:/app/data ghcr.io/xchronusx/carzty
```

The first one is the wizard, the second one runs it. Everything (config, database, logs) lives in the
`carzty-data` volume. Images are built for amd64 and arm64, so a Raspberry Pi works too.
With compose: `docker compose run --rm carzty setup`, then `docker compose up -d`.

### pipx

```bash
pipx install git+https://github.com/xchronusx/carzty.git
carzty setup
carzty
```

Config and data go in your user app folder (`%LOCALAPPDATA%\Carzty`, `~/Library/Application Support/Carzty`
or `~/.local/share/carzty`). Set `CARZTY_HOME` to put them somewhere else.

### By hand

```bash
git clone https://github.com/xchronusx/carzty.git && cd carzty
python3 -m venv .venv && . .venv/bin/activate      # windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m carzty setup
python -m carzty
```

Autostart, systemd, backups and updating are all in [docs/self-hosting.md](docs/self-hosting.md).

## Commands

Everything's a slash command, and every reply only shows up for you, so you're not spamming the channel.

| Command | What it does |
| --- | --- |
| `/task add` | Add a task. `what` is required, everything else is optional |
| `/task list` | Everything you've got going on |
| `/task show` | Full details on one task |
| `/task done` | Mark it done. If it isn't going off yet, it counts for the next one |
| `/task snooze` | Snooze the one that's going off. `for:30m` or `for:tomorrow 9am` |
| `/task skip` | Skip the next one, or dismiss the one going off |
| `/task pause` / `resume` | Shut it up for a while without deleting it |
| `/task edit` | Change anything. Only fill in what you want changed |
| `/task remove` | Gone for good |
| `/carzty timezone` | Set your timezone so "9am" means *your* 9am |
| `/carzty tone` | chill / salty / unhinged |
| `/carzty me` | Your settings and stats |
| `/carzty help` | Cheat sheet |
| `/carzty about` | Version, uptime |

The `task` option autocompletes from your own tasks, so you never have to remember an ID.

### Examples

```
/task add what:Stretch every:1h
/task add what:Standup notes every:weekdays when:8:45am
/task add what:Take out the trash every:mon,thu when:7pm deliver:Post in this channel
/task add what:Call the dentist when:tomorrow 10am nag:30m
/task add what:Water the plants every:3d when:6pm notes:The fern is dramatic, give it extra
```

Full reference with every option and edge case: [docs/commands.md](docs/commands.md)

### Times it understands

| Kind | Examples |
| --- | --- |
| `every` | `30m` `2h` `1h30m` `1d` `1w` `hourly` `daily` `weekly` `every other day` `weekdays` `weekends` `mon,wed,fri` `tue/thu` `mon-fri` `once` |
| `when` | `now` `in 20m` `20m` `9am` `9:30pm` `21:00` `noon` `midnight` `morning` `tonight` `tomorrow 8am` `friday 3pm` `next monday` `10/25 2pm` `oct 25 6pm` `25 oct` `2026-10-25 14:00` |
| `nag` / snooze `for` | any duration: `5m` `10m` `1h`. Snooze also takes times: `5pm`, `tomorrow 9am` |

Slash dates are US style (month/day). ISO (`2026-10-25`) works if you're one of those people.
A bare number like `9` gets rejected on purpose. 9am? 9pm? Use your words.

## Config

Everything lives in `.env`. The setup wizard writes it for you (token, timezone, tone, who's allowed),
and everything else has a sane default. Rerun the wizard any time, or edit `.env` by hand and restart.

| Setting | Default | What it does |
| --- | --- | --- |
| `DISCORD_TOKEN` | *(required)* | Your bot token |
| `DEFAULT_TIMEZONE` | `UTC` | Timezone for people who haven't run `/carzty timezone` |
| `DEFAULT_TONE` | `salty` | `chill`, `salty` or `unhinged` |
| `ALLOWED_USER_IDS` | *(anyone)* | Comma-separated Discord user IDs. Set this to keep the bot to yourself |
| `MAX_TASKS_PER_USER` | `50` | Open task limit per person |
| `MIN_INTERVAL` | `1m` | Shortest allowed `every` and `nag` |
| `MAX_NAGS` | `24` | Nags per reminder before it gives up |
| `SNOOZE_OPTIONS` | `15m,1h` | Snooze buttons on each reminder (max 3) |
| `TICK_SECONDS` | `10` | How often it checks for due reminders |
| `PURGE_DONE_AFTER_DAYS` | `30` | Delete finished one-time tasks after this long. `0` keeps them forever |
| `DATABASE_PATH` | `data/carzty.db` | SQLite file |
| `LOG_DIR` / `LOG_LEVEL` | `logs` / `INFO` | Rotating log at `logs/carzty.log` |
| `CARZTY_HOME` | repo folder | Where `.env`, `data/` and `logs/` live. Only matters for pipx installs or if you want them elsewhere |

## How it works

```
carzty/
├── core/              pure python, no discord in here
│   ├── timeparse.py   "tomorrow 9am" -> an actual datetime
│   ├── engine.py      all the scheduling rules: when to fire, nag, snooze, skip, catch up
│   ├── models.py      the Task dataclass
│   └── store.py       sqlite
├── cogs/              slash commands (/task, /carzty)
├── ui/                embeds + the persistent Done/Snooze/Skip buttons
├── scheduler.py       the loop: every tick, grab what's due, send it, save it
├── voice.py           the attitude
├── config.py          .env -> settings
├── setup_wizard.py    `carzty setup`: token, timezone, tone, invite link
└── bot.py             wires it together
scripts/windows/       one-line installer, setup, run (with auto-restart), autostart
scripts/linux/         one-line installer for linux + macOS
install.cmd, start.cmd double-click versions for windows
deploy/systemd/        system-wide linux service file
tests/                 ~200 tests, no Discord connection needed
```

The engine is just functions: a task goes in, a new task comes out. The scheduler and the
commands call it and save the result. That's why the tests can fake time and check stuff like
"does 9am stay 9am when New York falls back an hour" without waiting for November.

Slash commands only get re-synced with Discord when they actually change (it hashes them), so
restarting the bot 40 times while you're messing with it won't get you rate limited.

## Development

```bash
pip install -r requirements-dev.txt
python -m pytest     # tests
ruff check .         # lint
```

CI runs both on Linux (Python 3.10, 3.12, 3.13) and Windows, runs the installers on Linux, macOS and
Windows, runs PSScriptAnalyzer on the PowerShell scripts, and builds the Docker image. Pushes to `main`
publish the image to GHCR. PRs welcome, especially ones with better insults for `voice.py`.

## What it stores

Your Discord user ID, the task text and notes you typed, the schedule, which channel to post in
(if you picked one), and your timezone/tone settings. That's it. It lives in one SQLite file on
whatever machine runs the bot. No analytics, nothing phones home. Finished one-time tasks get
deleted after 30 days, and `/task remove` deletes immediately.

If you run a public instance, tell people that, because it's their data on your box.

## Troubleshooting

**Slash commands don't show up.** Give it a minute after first start, then hit `Ctrl+R` in Discord
to reload. Make sure the invite link included the `applications.commands` scope (the one the setup
wizard prints does). Still nothing? Run once with `--sync` (`carzty.run.zw.ps1 -Sync` or `python -m carzty run --sync`).

**Reminders never show up in DMs.** Discord's privacy settings for that server probably block DMs from
members. Server name → Privacy Settings → Direct Messages on. Or use `deliver:Post in this channel`.
`/task list` shows a ⚠️ on any task that failed to deliver, and `/task show` tells you why.

**"9am" was the wrong 9am.** Run `/carzty timezone`. Existing tasks keep their old times. Use
`/task edit` with a new `when` to fix them.

**It said the token is bad.** Developer Portal → your app → Bot → Reset Token, then run the wizard again
(`install.cmd` on Windows, `python -m carzty setup` everywhere else) and paste the new one.

**PowerShell says running scripts is disabled.** Use `install.cmd` / `start.cmd`, they get around it. Or
run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once.

## License

MIT. Do whatever you want with it. See [LICENSE](LICENSE).

Made by Zachary Wright ([@xchronusx](https://github.com/xchronusx)).
