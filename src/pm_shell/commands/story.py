from __future__ import annotations

from typing import Annotated, Optional

import typer
from rich.console import Console

from pm_shell.commands._context import resolve_story_key
from pm_shell.render.cards import story_card
from pm_shell.render.tables import story_table
from pm_shell.workspace.paths import resolve_context
from pm_shell.workspace.tree import (
    WorkspaceMissingError,
    list_stories,
    load_story,
    load_tasks,
    load_comments,
)

app = typer.Typer(help="Story operations.", no_args_is_help=True)
console = Console()
err_console = Console(stderr=True)


@app.command("list")
def story_list(
    epic: Annotated[
        Optional[str],
        typer.Option("--epic", "-e", help="Filter to stories under a specific epic key."),
    ] = None,
) -> None:
    """List stories. Filtered by --epic, or by cwd if inside an epic directory; otherwise all."""
    epic_key = epic
    if epic_key is None:
        cwd_epic, cwd_story = resolve_context()
        if cwd_epic and not cwd_story:
            epic_key = cwd_epic

    stories = list_stories(epic_key)
    if not stories:
        scope = f"epic {epic_key}" if epic_key else "workspace"
        console.print(f"[dim]no stories in {scope}[/dim]")
        return

    counts: dict[str, tuple[int, int]] = {}
    for s in stories:
        try:
            tasks = load_tasks(s["key"])
        except WorkspaceMissingError:
            tasks = []
        done = sum(1 for t in tasks if t.get("done"))
        counts[s["key"]] = (done, len(tasks))

    console.print(story_table(stories, counts))


@app.command("show")
def story_show(
    key: Annotated[Optional[str], typer.Argument(help="Story key (e.g. KAN-5). Inferred from cwd if omitted.")] = None,
) -> None:
    """Display a story card with task summary and most recent comment."""
    resolved = resolve_story_key(key)
    try:
        story = load_story(resolved)
        tasks = load_tasks(resolved)
        comments = load_comments(resolved)
    except WorkspaceMissingError as exc:
        err_console.print(f"[red]{exc}[/]")
        raise typer.Exit(code=1) from None
    latest = comments[-1] if comments else None
    console.print(story_card(story, tasks, latest))
