from __future__ import annotations

from typing import Annotated, Optional

import typer
from rich.console import Console

from pm_shell.commands._context import resolve_story_key
from pm_shell.render.comments import comment_panel, render_comment_list
from pm_shell.workspace.tree import WorkspaceMissingError, load_comments

app = typer.Typer(help="Comment operations.", no_args_is_help=True)
console = Console()
err_console = Console(stderr=True)


@app.command("list")
def comment_list(
    story: Annotated[
        Optional[str],
        typer.Argument(help="Story key. Inferred from cwd if omitted."),
    ] = None,
) -> None:
    """Print all comments for a story with author, timestamp, and body."""
    resolved = resolve_story_key(story)
    try:
        comments = load_comments(resolved)
    except WorkspaceMissingError as exc:
        err_console.print(f"[red]{exc}[/]")
        raise typer.Exit(code=1) from None
    console.print(render_comment_list(comments))


@app.command("last")
def comment_last(
    story: Annotated[
        Optional[str],
        typer.Argument(help="Story key. Inferred from cwd if omitted."),
    ] = None,
) -> None:
    """Print only the most recent comment for a story."""
    resolved = resolve_story_key(story)
    try:
        comments = load_comments(resolved)
    except WorkspaceMissingError as exc:
        err_console.print(f"[red]{exc}[/]")
        raise typer.Exit(code=1) from None
    if not comments:
        console.print(f"[dim]{resolved} has no comments[/dim]")
        return
    console.print(comment_panel(comments[-1]))
