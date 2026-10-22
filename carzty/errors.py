##xchronusx
"""
carzty.errors - the error a human is supposed to read.

Synopsis:
    raise Oops("You didn't change anything. Bold strategy.")

Description:
    Raise Oops (or EngineError / ParseError from core) anywhere inside a slash
    command and the tree's error handler sends the message back to the user,
    ephemeral, with a ❌ in front. No stack trace, no log spam.
    Anything else that blows up gets logged and the user gets a generic sorry.

Notes:
    Author: Zachary Wright (xchronusx)
"""

from __future__ import annotations

from carzty.core.engine import EngineError
from carzty.core.timeparse import ParseError


class Oops(Exception):
    """User-facing error. The message goes straight back to them."""


USER_ERRORS = (Oops, EngineError, ParseError)
##xchronusx
