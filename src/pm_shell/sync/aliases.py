from __future__ import annotations

import typer

STATUS_ALIASES: dict[str, str] = {
    "todo": "todo", "backlog": "todo", "open": "todo",
    "in-progress": "in-progress", "wip": "in-progress",
    "start": "in-progress", "started": "in-progress",
    "doing": "in-progress",
    "done": "done", "complete": "done", "completed": "done",
    "closed": "done", "finish": "done", "finished": "done",
    "blocked": "blocked", "block": "blocked", "hold": "blocked",
}

PRIORITY_ALIASES: dict[str, str] = {
    "low": "low",
    "medium": "medium", "med": "medium", "normal": "medium",
    "high": "high", "hi": "high",
    "critical": "critical", "crit": "critical", "blocker": "critical",
}

CANONICAL_STATUSES = ("todo", "in-progress", "done", "blocked")
CANONICAL_PRIORITIES = ("low", "medium", "high", "critical")


def canonicalize_status(value: str) -> str:
    canonical = STATUS_ALIASES.get(value.strip().lower())
    if canonical is None:
        raise typer.BadParameter(
            f"Unknown status '{value}'. Expected one of: {', '.join(CANONICAL_STATUSES)} "
            f"(aliases: {', '.join(sorted(STATUS_ALIASES))})."
        )
    return canonical


def canonicalize_priority(value: str) -> str:
    canonical = PRIORITY_ALIASES.get(value.strip().lower())
    if canonical is None:
        raise typer.BadParameter(
            f"Unknown priority '{value}'. Expected one of: {', '.join(CANONICAL_PRIORITIES)}."
        )
    return canonical
