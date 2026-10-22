##xchronusx
"""
carzty.logs - logging setup. console + a rotating file.

Synopsis:
    setup_logging(level="INFO", log_dir=Path("logs"))

Description:
    Console gets the short version, logs/carzty.log gets everything with
    timestamps. File rotates at 5 MB and keeps 5 old ones, so it can't eat your
    disk while you're not looking.

Notes:
    Author: Zachary Wright (xchronusx)
    discord.py is chatty at DEBUG. we pin its loggers to INFO unless you really mean it.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(level: str = "INFO", log_dir: Path | None = None) -> Path | None:
    root = logging.getLogger()
    root.setLevel(level)
    for handler in list(root.handlers):
        root.removeHandler(handler)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%H:%M:%S"))
    root.addHandler(console)

    log_file = None
    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "carzty.log"
        fh = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
        root.addHandler(fh)

    if level != "DEBUG":
        logging.getLogger("discord").setLevel(logging.INFO)
        logging.getLogger("discord.http").setLevel(logging.WARNING)
        logging.getLogger("discord.gateway").setLevel(logging.WARNING)
    return log_file
##xchronusx
