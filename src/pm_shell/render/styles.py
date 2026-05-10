from __future__ import annotations

from typing import Optional

STATUS_STYLE = {
    "todo": "dim",
    "in-progress": "yellow",
    "done": "green",
    "blocked": "red",
}

PRIORITY_STYLE = {
    "low": "blue",
    "medium": "cyan",
    "high": "yellow",
    "critical": "red",
}


def style_status(status: Optional[str], jira_name: Optional[str] = None) -> str:
    label = status or jira_name or "—"
    style = STATUS_STYLE.get(status or "", "magenta")
    return f"[{style}]{label}[/{style}]"


def style_priority(priority: Optional[str]) -> str:
    if not priority:
        return "[dim]—[/dim]"
    style = PRIORITY_STYLE.get(priority.lower(), "white")
    return f"[{style}]{priority}[/{style}]"


def user_label(user: Optional[dict]) -> str:
    if not user:
        return "[dim]—[/dim]"
    return user.get("displayName") or user.get("email") or user.get("accountId") or "[dim]?[/dim]"
