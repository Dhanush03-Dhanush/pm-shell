from __future__ import annotations

import re
from typing import Annotated, Optional

import typer
from rich.console import Console

from pm_shell.commands._context import resolve_story_key
from pm_shell.commands._editor import open_editor
from pm_shell.commands._mutate import append_comment
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


_KEY_RE = re.compile(r"^[A-Z][A-Z0-9]*-\d+$")


def _split_story_and_text(arg1: Optional[str], arg2: Optional[str]) -> tuple[str, Optional[str]]:
    if arg1 is None:
        return resolve_story_key(None), None
    if arg2 is None:
        if _KEY_RE.match(arg1):
            return arg1, None
        return resolve_story_key(None), arg1
    if not _KEY_RE.match(arg1):
        raise typer.BadParameter(f"Expected a story key, got {arg1!r}")
    return arg1, arg2


@app.command("add")
def comment_add(
    arg1: Annotated[Optional[str], typer.Argument(help="Story key (optional) or inline body.")] = None,
    arg2: Annotated[Optional[str], typer.Argument(help="Inline body (when story key is given first).")] = None,
) -> None:
    """Append a comment to a story. Opens $EDITOR when no inline text is given."""
    story_key, body = _split_story_and_text(arg1, arg2)
    if body is None:
        body = open_editor("", suffix=".md")
        if not body:
            console.print("[dim]no comment[/]")
            return

    try:
        record = append_comment(story_key, body)
    except WorkspaceMissingError as exc:
        err_console.print(f"[red]{exc}[/]")
        raise typer.Exit(code=1) from None
    console.print(f"[green]+[/] {story_key} comment queued ({record['id']})")
