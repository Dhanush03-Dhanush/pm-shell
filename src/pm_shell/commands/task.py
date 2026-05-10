from __future__ import annotations

from typing import Annotated, Optional

import typer
from rich.console import Console

from pm_shell.commands._context import resolve_story_key
from pm_shell.render.tables import task_table
from pm_shell.workspace.tree import WorkspaceMissingError, load_tasks

app = typer.Typer(help="Task (sub-task) operations.", no_args_is_help=True)
console = Console()
err_console = Console(stderr=True)


@app.command("list")
def task_list(
    story: Annotated[
        Optional[str],
        typer.Argument(help="Story key. Inferred from cwd if omitted."),
    ] = None,
) -> None:
    """List tasks for a story with ID, title, and done status."""
    resolved = resolve_story_key(story)
    try:
        tasks = load_tasks(resolved)
    except WorkspaceMissingError as exc:
        err_console.print(f"[red]{exc}[/]")
        raise typer.Exit(code=1) from None
    if not tasks:
        console.print(f"[dim]{resolved} has no tasks[/dim]")
        return
    console.print(task_table(tasks))
