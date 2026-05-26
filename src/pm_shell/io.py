"""Shared rich Console instances. Don't construct ad-hoc Console() objects in
command modules — the TUI relies on capturing these via `console.capture()`."""

from __future__ import annotations

import os

from rich.console import Console

# force_terminal so capture() yields ANSI even off a real TTY (needed for the TUI).
_FORCE_TERMINAL = os.environ.get("PM_SHELL_NO_COLOR") != "1"

console = Console(force_terminal=_FORCE_TERMINAL)
err_console = Console(stderr=True, force_terminal=_FORCE_TERMINAL)
