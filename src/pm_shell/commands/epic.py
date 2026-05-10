from __future__ import annotations

from typing import Annotated, Optional

import typer
from rich.console import Console

from pm_shell.commands._context import resolve_epic_key
from pm_shell.render.cards import epic_card
from pm_shell.render.tables import epic_table
from pm_shell.workspace.tree import (
    WorkspaceMissingError,
    list_epics,
    load_epic,
    stories_for_epic,
)

app = typer.Typer(help="Epic operations.", no_args_is_help=True)
console = Console()
err_console = Console(stderr=True)


@app.command("list")
def epic_list() -> None:
    """List all epics with status, priority, story count, and owner."""
    epics = list_epics()
    if not epics:
        console.print("[dim]no epics in workspace[/dim]")
        return
    counts = {e["key"]: len(stories_for_epic(e["key"])) for e in epics}
    console.print(epic_table(epics, counts))


@app.command("show")
def epic_show(
    key: Annotated[Optional[str], typer.Argument(help="Epic key (e.g. KAN-4). Inferred from cwd if omitted.")] = None,
) -> None:
    """Display a formatted card for an epic with its story summary list."""
    resolved = resolve_epic_key(key)
    try:
        epic = load_epic(resolved)
    except WorkspaceMissingError as exc:
        err_console.print(f"[red]{exc}[/]")
        raise typer.Exit(code=1) from None
    stories = stories_for_epic(resolved)
    console.print(epic_card(epic, stories))
