"""Startup banner shared by the Textual TUI and the simple REPL.

One source of truth for the pixel-art logo and the version/status line that
follows it, so both shell surfaces look identical and the art only has to be
maintained once.
"""

from __future__ import annotations

from typing import Optional

from rich.console import Group
from rich.text import Text


# Half-block "pixel" rendering of "PM·SHELL". Two rows keeps it compact
# enough for any terminal width (~33 cols) and avoids wrapping in narrow
# panes. Each character is hand-aligned; if you edit a row, edit both.
_LOGO_ROWS: tuple[str, ...] = (
    "█▀█ █▀▄▀█   █▀ █ █ █▀▀ █   █  ",
    "█▀▀ █ ▀ █   ▄█ █▀█ █▄▄ █▄▄ █▄▄",
)
_TAGLINE = "a git-like shell for Jira boards"
_TAGLINE_STYLE = "dim italic"

# Horizontal gradient applied per-column across both logo rows: turquoise on
# the left, deep blue on the right. Tuples are (R, G, B), 0–255.
_GRADIENT_START: tuple[int, int, int] = (64, 224, 208)   # #40E0D0 turquoise
_GRADIENT_END:   tuple[int, int, int] = (38, 96, 235)    # #2660EB cobalt blue


def _gradient_row(row: str) -> Text:
    """Color each column of a logo row by interpolating start→end RGB.

    Truecolor (24-bit) is used; Rich automatically downsamples on terminals
    that only support 256 colors, so this stays readable everywhere.
    """
    text = Text()
    span = max(len(row) - 1, 1)
    for i, char in enumerate(row):
        t = i / span
        r = round(_GRADIENT_START[0] + (_GRADIENT_END[0] - _GRADIENT_START[0]) * t)
        g = round(_GRADIENT_START[1] + (_GRADIENT_END[1] - _GRADIENT_START[1]) * t)
        b = round(_GRADIENT_START[2] + (_GRADIENT_END[2] - _GRADIENT_START[2]) * t)
        text.append(char, style=f"bold rgb({r},{g},{b})")
    return text


def project_from_url(base_url: Optional[str]) -> str:
    """Extract the tenant subdomain from a Jira base URL ('acme' from 'https://acme.atlassian.net')."""
    if not base_url:
        return "?"
    try:
        return base_url.split("//", 1)[-1].split(".", 1)[0]
    except (IndexError, AttributeError):
        return "?"


def banner(
    *,
    version: str,
    project: Optional[str] = None,
    epic_count: Optional[int] = None,
    story_count: Optional[int] = None,
) -> Group:
    """Build the startup banner as a Rich renderable.

    Works in both `console.print(...)` (REPL) and `RichLog.write(...)` (TUI).
    Pass `project=None` to render the no-workspace variant with a setup hint.
    """
    parts: list[Text] = [_gradient_row(row) for row in _LOGO_ROWS]
    parts.append(Text(_TAGLINE, style=_TAGLINE_STYLE))
    parts.append(Text(""))  # blank line between art and status
    parts.append(_status_line(version, project, epic_count, story_count))
    parts.append(_hint_line(project is not None))
    return Group(*parts)


def _status_line(
    version: str,
    project: Optional[str],
    epic_count: Optional[int],
    story_count: Optional[int],
) -> Text:
    line = Text()
    line.append(f"v{version}", style="bold")
    line.append("  ·  ", style="dim")
    if project is None:
        line.append("no workspace", style="yellow")
        return line
    line.append(project, style="cyan")
    if epic_count is not None and story_count is not None:
        line.append("  ·  ", style="dim")
        line.append(f"{epic_count} epics, {story_count} stories", style="dim")
    return line


def _hint_line(has_workspace: bool) -> Text:
    if has_workspace:
        return Text("type `help` for commands, `exit` to quit", style="dim")
    return Text(
        "run `config init --from <secrets.json>` then `clone` to start",
        style="dim",
    )
