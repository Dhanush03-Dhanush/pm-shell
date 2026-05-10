from __future__ import annotations

from typing import Optional

import typer

from pm_shell.workspace.paths import resolve_context


def resolve_epic_key(explicit: Optional[str]) -> str:
    if explicit:
        return explicit
    epic_key, _ = resolve_context()
    if epic_key:
        return epic_key
    raise typer.BadParameter(
        "Epic key required. Pass it explicitly or run from inside an epic directory."
    )


def resolve_story_key(explicit: Optional[str]) -> str:
    if explicit:
        return explicit
    _, story_key = resolve_context()
    if story_key:
        return story_key
    raise typer.BadParameter(
        "Story key required. Pass it explicitly or run from inside a story directory."
    )
