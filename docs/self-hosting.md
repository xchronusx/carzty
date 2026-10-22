# Self-hosting

Carzty is one Python process and one SQLite file. Run it wherever you've got a machine that stays on.
It needs outbound HTTPS to Discord and nothing else. No ports to open, no reverse proxy, no domain.

## Windows

The one-liner (PowerShell):

```powershell
irm https://raw.githubusercontent.com/xchronusx/carzty/main/scripts/windows/carzty.install.zw.ps1 | iex
```

Want it somewhere other than `%USERPROFILE%\Carzty`?

```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/xchronusx/carzty/main/scripts/windows/carzty.install.zw.ps1))) -InstallDir D:\Bots\Carzty
```

Or download the ZIP, unzip it wherever, double-click `install.cmd`.

What's in the box:

| File | What it does |
| --- | --- |
| `install.cmd` | Double-click version of setup. Rerun it to change settings or after updating |
| `start.cmd` | Double-click to run it in a window. Close the window to stop it |
| `scripts\windows\carzty.install.zw.ps1` | The one-liner. Downloads (or `git pull`s) the code, then runs setup |
| `scripts\windows\carzty.setup.zw.ps1` | Finds Python (installs 3.12 with winget if missing), builds `.venv`, installs packages, runs the wizard, runs `check`, offers autostart. `-Dev` adds test tools, `-Force` rebuilds the venv, `-NoPrompt` for scripts |
| `scripts\windows\carzty.run.zw.ps1` | Runs the bot and restarts it with backoff if it crashes. Won't restart on a bad token or bad config, because that just loops forever. `-NoRestart`, `-MaxRestarts N`, `-Sync` |
| `scripts\windows\carzty.autostart.zw.ps1` | `-Install` adds a scheduled task that runs at logon, as you. `-Install -AtStartup` (admin) runs at boot as SYSTEM, even with nobody logged in. `-Remove`, or no switch for status |

Launcher logs go to `C:\Temp\carzty.*_<timestamp>.log`. The bot's own log is `logs\carzty.log` in the
install folder. If `-Install` says access denied, run it from an admin PowerShell.

## Linux / macOS

The one-liner:

```bash
curl -fsSL https://raw.githubusercontent.com/xchronusx/carzty/main/scripts/linux/carzty.install.zw.sh | bash
```

Knobs, if you need them (set them in front of `bash`, like `curl ... | CARZTY_DIR=/srv/carzty bash`):

| Variable | What it does |
| --- | --- |
| `CARZTY_DIR` | Install folder. Default `~/carzty` |
| `CARZTY_BRANCH` | Branch to grab. Default `main` |
| `CARZTY_TOKEN` | Bot token. Makes the whole install unattended, no questions |
| `CARZTY_NO_SERVICE=1` | Don't offer the systemd service |

On Linux with systemd it offers a **user service** (`~/.config/systemd/user/carzty.service`):

```bash
journalctl --user -u carzty -f        # logs
systemctl --user restart carzty       # restart
systemctl --user disable --now carzty # stop it for good
```

It also offers to turn on *linger* for your user, which is what keeps user services running after you log
out and starts them at boot. On a Mac there's no service, so run it in tmux/screen or use Docker.

### System-wide service instead

If you'd rather run it as its own locked-down system user, there's a unit for that:

```bash
sudo useradd --system --home /opt/carzty --shell /usr/sbin/nologin carzty
sudo git clone https://github.com/xchronusx/carzty.git /opt/carzty
cd /opt/carzty
sudo python3 -m venv .venv
sudo .venv/bin/pip install -r requirements.txt
sudo .venv/bin/python -m carzty setup
sudo mkdir -p data logs && sudo chown -R carzty:carzty /opt/carzty
sudo cp deploy/systemd/carzty.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now carzty
journalctl -u carzty -f
```

That unit gets a read-only filesystem except `data/` and `logs/`, no new privileges, and won't
restart-loop on a bad token.

## Docker

No clone needed:

```bash
docker run --rm -it -v carzty-data:/app/data ghcr.io/xchronusx/carzty setup
docker run -d --name carzty --restart unless-stopped -v carzty-data:/app/data ghcr.io/xchronusx/carzty
docker logs -f carzty
```

Rather skip the wizard? Pass settings as environment variables instead:

```bash
docker run -d --name carzty --restart unless-stopped \
  -e DISCORD_TOKEN=your-token-here \
  -e DEFAULT_TIMEZONE=America/Phoenix \
  -v carzty-data:/app/data ghcr.io/xchronusx/carzty
```

Environment variables win over whatever's in `.env`.

With compose (there's a `docker-compose.yml` in the repo):

```bash
docker compose run --rm carzty setup
docker compose up -d
```

Want to build it yourself instead of pulling? Uncomment `build: .` in the compose file, or
`docker build -t carzty .`. Works the same on a Proxmox VM/LXC with Docker, TrueNAS, Unraid, a Pi...

## Updating

| How you installed | How you update |
| --- | --- |
| Windows one-liner | Run the one-liner again |
| ZIP | Download the new ZIP, unzip over the old folder, run `install.cmd` |
| Linux/macOS one-liner | Run the one-liner again (it restarts the service for you) |
| Docker | `docker pull ghcr.io/xchronusx/carzty` then recreate the container (`docker compose pull && docker compose up -d`) |
| pipx | `pipx reinstall carzty` |
| git | `git pull`, `pip install -r requirements.txt`, restart |

Your `.env`, database and logs are never touched by an update. The database upgrades itself on startup
(schema version lives in `PRAGMA user_version`), and slash commands re-sync on their own when they change.

## Backups

Everything is in `data/carzty.db` (in Docker: the `carzty-data` volume). The bot runs SQLite in WAL mode,
so to grab a clean copy while it's running:

```bash
sqlite3 data/carzty.db ".backup 'carzty-backup.db'"
```

Or stop the bot and copy the file. Restoring = stop the bot, put the file back, start the bot.

## Command line

```
carzty                  run it (same as `carzty run`)
carzty setup            the wizard. --token --timezone --tone --lock/--no-lock --yes --no-verify
carzty check            check .env + database, then exit (no token needed)
carzty run --sync       run it and force a slash command sync
carzty --env PATH       use a different .env file
carzty --version
```

From a checkout without pipx, it's `python -m carzty ...` (or `.venv\Scripts\python.exe -m carzty ...` on
Windows). Exit codes: `0` fine, `1` bad config, `2` bad token, `3` crashed or can't reach Discord.
