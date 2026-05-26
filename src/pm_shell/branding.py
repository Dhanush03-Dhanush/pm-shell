"""Startup banner shared by the Textual TUI and the simple REPL."""

from __future__ import annotations

from typing import Optional

from rich.console import Group
from rich.text import Text


# Half-block "PM·SHELL" — ~33 cols, hand-aligned per char (edit both rows together).
_LOGO_ROWS: tuple[str, ...] = (
    "█▀█ █▀▄▀█   █▀ █ █ █▀▀ █   █  ",
    "█▀▀ █ ▀ █   ▄█ █▀█ █▄▄ █▄▄ █▄▄",
)
_TAGLINE = "a git-like shell for Jira boards"
_TAGLINE_STYLE = "dim italic"

_GRADIENT_START: tuple[int, int, int] = (64, 224, 208)   # #40E0D0 turquoise
_GRADIENT_END:   tuple[int, int, int] = (38, 96, 235)    # #2660EB cobalt blue


def _gradient_row(row: str) -> Text:
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
    # 'acme' from 'https://acme.atlassian.net'.
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
    # project=None renders the no-workspace variant with a setup hint.
    parts: list[Text] = [_gradient_row(row) for row in _LOGO_ROWS]
    parts.append(Text(_TAGLINE, style=_TAGLINE_STYLE))
    parts.append(Text(""))
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
    if epic_count is not None and story_count is not None:
        line.append(f"{epic_count} epics, {story_count} stories", style="dim")
    return line


def _hint_line(has_workspace: bool) -> Text:
    if has_workspace:
        return Text("type `help` for commands, `exit` to quit", style="dim")
    return Text(
        "run `config init --from <secrets.json>` then `clone` to start",
        style="dim",
    )
