from __future__ import annotations

from typing import Any

from rich.console import Group
from rich.panel import Panel
from rich.text import Text

from pm_shell.render.adf import adf_to_plain
from pm_shell.render.styles import user_label


def comment_panel(comment: dict[str, Any], *, label: str = "") -> Panel:
    author = user_label(comment.get("author"))
    when = comment.get("created") or ""
    header = f"{author}  [dim]{when}[/dim]"
    if label:
        header = f"[dim]{label}[/dim]  {header}"
    body = adf_to_plain(comment.get("body")).strip() or "[dim](empty)[/dim]"
    return Panel(Group(Text.from_markup(header), Text(""), Text(body)), border_style="dim")


def render_comment_list(comments: list[dict[str, Any]]) -> Group:
    if not comments:
        return Group(Text("[dim]no comments[/dim]"))
    panels = [comment_panel(c) for c in comments]
    return Group(*panels)
