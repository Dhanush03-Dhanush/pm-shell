from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.tree import Tree

from pm_shell.config import workspace_dir
from pm_shell.render.cards import epic_card, story_card
from pm_shell.render.styles import style_priority, style_status, user_label
from pm_shell.render.tables import epic_table, story_table, task_table
from pm_shell.workspace.io import read_json
from pm_shell.workspace.paths import (
    parse_key_from_dirname,
    resolve_context,
    resolve_workspace_target,
)
from pm_shell.workspace.tree import (
    list_epics,
    list_stories,
    load_comments,
    load_epic,
    load_story,
    load_tasks,
    stories_for_epic,
)

console = Console()
err_console = Console(stderr=True)


def _classify(path: Path) -> tuple[str, Optional[str], Optional[str]]:
    """Return (kind, epic_key, story_key) for a path inside .jira/.

    kind ∈ {"workspace", "epics_root", "epic", "story", "unparented_root", "outside"}.
    """
    p = path.resolve()
    ws = workspace_dir().resolve()
    try:
        rel = p.relative_to(ws)
    except ValueError:
        return ("outside", None, None)
    parts = rel.parts
    if not parts:
        return ("workspace", None, None)
    if parts[0] == "epics":
        if len(parts) == 1:
            return ("epics_root", None, None)
        epic_key = parse_key_from_dirname(parts[1])
        if len(parts) == 2:
            return ("epic", epic_key, None)
        story_key = parse_key_from_dirname(parts[2])
        return ("story", epic_key, story_key)
    if parts[0] == "unparented":
        if len(parts) == 1:
            return ("unparented_root", None, None)
        story_key = parse_key_from_dirname(parts[1])
        return ("story", None, story_key)
    return ("outside", None, None)


def _resolve_target(arg: Optional[str]) -> tuple[Path, bool]:
    """Resolve a CLI target into (path, was_explicit). Accepts a Jira key or a path.

    `was_explicit` is True when the user supplied an argument (so we error on missing dirs
    instead of falling back to the workspace root).
    """
    if arg is None:
        return Path.cwd().resolve(), False
    resolved = resolve_workspace_target(arg)
    if resolved is not None:
        return resolved.resolve(), True
    return Path(arg).expanduser().resolve(), True


def ls(
    target: Annotated[
        Optional[str],
        typer.Argument(help="Path or Jira key (e.g. KAN-4). Defaults to cwd."),
    ] = None,
) -> None:
    """List contents of the current (or given) workspace directory with inline metadata."""
    resolved, explicit = _resolve_target(target)
    kind, epic_key, story_key = _classify(resolved)

    if kind == "outside":
        if explicit:
            err_console.print(f"[red]{resolved} is outside the .jira workspace.[/]")
            raise typer.Exit(code=1)
        kind = "workspace"  # default fallback when invoked from outside

    if kind in ("workspace", "epics_root"):
        epics = list_epics()
        if not epics:
            console.print("[dim]no epics in workspace[/dim]")
            return
        counts = {e["key"]: len(stories_for_epic(e["key"])) for e in epics}
        console.print(epic_table(epics, counts))
        return

    if kind == "epic" and epic_key:
        epic = load_epic(epic_key)
        console.print(
            f"[bold cyan]{epic['key']}[/]  {epic.get('summary', '')}  "
            f"{style_status(epic.get('status'), epic.get('statusJira'))}  "
            f"{style_priority(epic.get('priority'))}  "
            f"owner: {user_label(epic.get('owner'))}"
        )
        stories = stories_for_epic(epic_key)
        if not stories:
            console.print("[dim]  no stories[/dim]")
            return
        counts = {}
        for s in stories:
            tasks = load_tasks(s["key"])
            counts[s["key"]] = (sum(1 for t in tasks if t.get("done")), len(tasks))
        console.print(story_table(stories, counts))
        return

    if kind == "story" and story_key:
        story = load_story(story_key)
        tasks = load_tasks(story_key)
        comments = load_comments(story_key)
        console.print(
            f"[bold magenta]{story['key']}[/]  {story.get('summary', '')}  "
            f"{style_status(story.get('status'), story.get('statusJira'))}  "
            f"{style_priority(story.get('priority'))}  "
            f"assignee: {user_label(story.get('assignee'))}"
        )
        done = sum(1 for t in tasks if t.get("done"))
        console.print(
            f"[dim]tasks {done}/{len(tasks)}  ·  comments {len(comments)}[/dim]"
        )
        if tasks:
            console.print(task_table(tasks))
        return

    if kind == "unparented_root":
        stories = list_stories()
        unparented = [s for s in stories if not s.get("epic")]
        if not unparented:
            console.print("[dim]no unparented stories[/dim]")
            return
        counts = {}
        for s in unparented:
            tasks = load_tasks(s["key"])
            counts[s["key"]] = (sum(1 for t in tasks if t.get("done")), len(tasks))
        console.print(story_table(unparented, counts))
        return


def _epic_tree_node(root: Tree, epic: dict) -> None:
    node = root.add(
        f"[cyan]{epic['key']}[/]  {epic.get('summary', '')}  "
        f"{style_status(epic.get('status'), epic.get('statusJira'))}  "
        f"{style_priority(epic.get('priority'))}"
    )
    for s in stories_for_epic(epic["key"]):
        _story_tree_node(node, s)


def _story_tree_node(parent: Tree, story: dict) -> None:
    tasks = load_tasks(story["key"])
    done = sum(1 for t in tasks if t.get("done"))
    node = parent.add(
        f"[magenta]{story['key']}[/]  {story.get('summary', '')}  "
        f"{style_status(story.get('status'), story.get('statusJira'))}  "
        f"[dim]{done}/{len(tasks)}[/]"
    )
    for t in tasks:
        check = "[green]✓[/]" if t.get("done") else "[dim]·[/]"
        node.add(f"{check} [dim]{t.get('key', '')}[/]  {t.get('title', '')}")


def tree(
    target: Annotated[
        Optional[str],
        typer.Argument(help="Path or Jira key (e.g. KAN-4). Defaults to cwd."),
    ] = None,
) -> None:
    """Recursive annotated tree from cwd (or a given workspace path/key)."""
    resolved, explicit = _resolve_target(target)
    kind, epic_key, story_key = _classify(resolved)
    if kind == "outside" and explicit:
        err_console.print(f"[red]{resolved} is outside the .jira workspace.[/]")
        raise typer.Exit(code=1)

    if kind == "story" and story_key:
        story = load_story(story_key)
        root = Tree(f"[bold magenta]{story['key']}[/]  {story.get('summary', '')}")
        tasks = load_tasks(story_key)
        for t in tasks:
            check = "[green]✓[/]" if t.get("done") else "[dim]·[/]"
            root.add(f"{check} [dim]{t.get('key', '')}[/]  {t.get('title', '')}")
        console.print(root)
        return

    if kind == "epic" and epic_key:
        epic = load_epic(epic_key)
        root = Tree(f"[bold cyan]{epic['key']}[/]  {epic.get('summary', '')}")
        for s in stories_for_epic(epic_key):
            _story_tree_node(root, s)
        console.print(root)
        return

    epics = list_epics()
    if not epics:
        console.print("[dim]workspace is empty[/dim]")
        return
    root = Tree("[bold].jira/epics/[/]")
    for e in epics:
        _epic_tree_node(root, e)
    console.print(root)


def show() -> None:
    """Smart display: epic card in an epic dir, story card in a story dir."""
    epic_key, story_key = resolve_context()
    if story_key:
        story = load_story(story_key)
        tasks = load_tasks(story_key)
        comments = load_comments(story_key)
        latest = comments[-1] if comments else None
        console.print(story_card(story, tasks, latest))
        return
    if epic_key:
        epic = load_epic(epic_key)
        stories = stories_for_epic(epic_key)
        console.print(epic_card(epic, stories))
        return
    err_console.print(
        "[yellow]No context.[/] Run from inside an epic or story directory, "
        "or use `pm epic show KEY` / `pm story show KEY`."
    )
    raise typer.Exit(code=1)
