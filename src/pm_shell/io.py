"""Shared rich Console instances.

Every command imports `console` and `err_console` from here so the TUI can
capture all command output via `console.capture()` without monkeypatching
each module. Don't construct ad-hoc Console() objects in command modules.
"""

from __future__ import annotations

import os

from rich.console import Console

# force_terminal=True so console.capture() yields ANSI-coloured text even when
# the captured output isn't going to a real terminal — critical for the TUI,
# which feeds captured output into Textual's RichLog via Text.from_ansi().
_FORCE_TERMINAL = os.environ.get("PM_SHELL_NO_COLOR") != "1"

console = Console(force_terminal=_FORCE_TERMINAL)
err_console = Console(stderr=True, force_terminal=_FORCE_TERMINAL)
