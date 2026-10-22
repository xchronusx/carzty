##xchronusx
"""
carzty.__main__ - `python -m carzty` (or just `carzty` if you pip/pipx installed it) lands here.

Synopsis:
    carzty                  run the bot
    carzty setup            the wizard: token, timezone, tone, lock it to you. writes .env
    carzty check            validate .env + database, then exit (no token needed)
    carzty run --sync       run it and force a slash command re-sync
    carzty --version

Description:
    Loads .env from CARZTY_HOME (the repo folder when you run from a checkout),
    sets up logging, opens the database, and runs the bot until you Ctrl+C it.
    No .env yet and you're at a keyboard? It offers to run setup first.

Notes:
    Author: Zachary Wright (xchronusx)
    Exit codes: 0 fine, 1 bad config, 2 bad token, 3 something else died, 130 you hit Ctrl+C in setup.
    `--check` still works as an alias for `check`, because old habits.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from carzty import __version__
from carzty.config import ConfigError, app_home, load_config
from carzty.logs import setup_logging


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="carzty", description="A Discord bot that nags you until you do the thing.")
    p.add_argument("command", nargs="?", default="run", choices=("run", "setup", "check"), help="what to do (default: run)")
    p.add_argument("--env", type=Path, default=None, help="path to the .env file (default: CARZTY_HOME/.env)")
    p.add_argument("--check", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--sync", action="store_true", help="run: force a slash command sync with Discord")
    p.add_argument("--version", action="version", version=f"carzty {__version__}")

    s = p.add_argument_group("setup options (all optional, the wizard asks for anything you leave out)")
    s.add_argument("--token", help="bot token")
    s.add_argument("--timezone", help="IANA timezone, like America/Phoenix")
    s.add_argument("--tone", choices=("chill", "salty", "unhinged"))
    lock = s.add_mutually_exclusive_group()
    lock.add_argument("--lock", dest="lock", action="store_true", default=None, help="only the bot's owner can use it")
    lock.add_argument("--no-lock", dest="lock", action="store_false", help="anyone can use it")
    s.add_argument("--yes", "-y", action="store_true", help="take the default answer for everything")
    s.add_argument("--no-verify", action="store_true", help="don't check the token with Discord")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    command = "check" if args.check else args.command
    env_path = args.env or (app_home() / ".env")

    #region SETUP

    if command == "setup":
        from carzty.setup_wizard import run_setup

        return run_setup(
            env_path, token=args.token, timezone=args.timezone, tone=args.tone, lock=args.lock, yes=args.yes, verify=not args.no_verify
        )

    # first run, no config, somebody's at the keyboard? just do the setup instead of yelling about it
    if command == "run" and not env_path.exists() and sys.stdin.isatty():
        print(f"No config at {env_path} yet. Let's fix that.")
        from carzty.setup_wizard import run_setup

        code = run_setup(env_path)
        if code != 0:
            return code

    #endregion

    #region CONFIG + LOGGING

    if env_path.exists():
        load_dotenv(env_path, override=False)

    try:
        config = load_config(require_token=command != "check")
    except ConfigError as exc:
        print(f"config problem: {exc}", file=sys.stderr)
        print("run `carzty setup` (or `python -m carzty setup`) to fix it the easy way.", file=sys.stderr)
        return 1

    log_file = setup_logging(config.log_level, config.log_dir)
    log = logging.getLogger("carzty")
    log.info("==== CARZTY v%s STARTING ====", __version__)
    log.info("config: %s | database: %s | logs: %s", env_path, config.database_path, log_file)
    log.info("default tz: %s | tone: %s", config.default_tz, config.default_tone)

    from carzty.core.store import Store

    store = Store(config.database_path)
    log.info("database schema v%s, %s task(s) on file", store.schema_version, store.stats()["total"])

    if command == "check":
        print(f"config looks good. token {'set' if config.token else 'NOT set'}. database OK at {config.database_path}")
        store.close()
        return 0

    #endregion

    #region RUN

    import aiohttp
    import discord

    from carzty.bot import CarztyBot  # here so setup/check don't drag discord's whole world in for nothing

    bot = CarztyBot(config, store, force_sync=args.sync)
    try:
        bot.run(config.token, log_handler=None)
    except discord.LoginFailure:
        log.error("Discord rejected the token. Reset it in the developer portal, then run `carzty setup`.")
        return 2
    except discord.PrivilegedIntentsRequired:
        log.error("Discord says we need privileged intents. We shouldn't. File a bug.")
        return 3
    except (aiohttp.ClientConnectionError, OSError) as exc:
        log.error("Can't reach Discord (%s). Internet down? Firewall? It'll get restarted and try again.", exc)
        return 3
    except Exception:  # noqa: BLE001
        log.exception("carzty died")
        return 3
    finally:
        log.info("==== CARZTY STOPPED ====")
    return 0

    #endregion


if __name__ == "__main__":
    sys.exit(main())
##xchronusx
