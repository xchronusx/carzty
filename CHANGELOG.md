# Changelog

## 1.0.0 - 2026-10-21

First release.

- `/task add | list | show | done | snooze | skip | pause | resume | edit | remove`
- `/carzty timezone | tone | me | help | about`
- Recurring schedules: intervals, whole-day intervals that survive DST, weekday sets
- One-time reminders with a pretty forgiving time parser
- Nag mode with escalating messages and a give-up limit
- Persistent Done / Snooze / Skip buttons
- DM or channel delivery, with DM fallback when the channel goes away
- Works as a server bot and a user-installed app
- Three tones: chill, salty, unhinged
- SQLite storage with self-running migrations
- `carzty setup` wizard: checks the token with Discord, detects your timezone, offers to lock the bot
  to its owner, prints the invite links
- One-line installers for Windows (PowerShell) and Linux/macOS (bash), plus double-click
  `install.cmd` / `start.cmd`
- Windows run (auto-restart) and autostart scripts, systemd user + system services
- Prebuilt multi-arch Docker image on GHCR
- pipx support (config goes in your user app folder)
- CI on Linux, macOS + Windows, including the installers
