from __future__ import annotations

import re
from typing import Annotated, Optional

import typer

from pm_shell.commands._context import resolve_story_key
from pm_shell.commands._editor import open_editor
from pm_shell.commands._mutate import (
    apply_status,
    load_and_save_tasks,
    renumber_tasks,
)
from pm_shell.config import load_config
from pm_shell.io import console, err_console
from pm_shell.render.tables import task_table
from pm_shell.workspace.tree import WorkspaceMissingError, load_tasks

app = typer.Typer(help="Task (sub-task) operations.", no_args_is_help=True)

_KEY_RE = re.compile(r"^[A-Z][A-Z0-9]*-\d+$")


def _split_story_id(arg1: Optional[str], arg2: Optional[str]) -> tuple[str, int]:
    if arg1 is None and arg2 is None:
        raise typer.BadParameter("Task ID required.")
    if arg2 is None:
        if arg1 and _KEY_RE.match(arg1):
            raise typer.BadParameter("Task ID required after story key.")
        try:
            return resolve_story_key(None), int(arg1)  # type: ignore[arg-type]
        except ValueError:
            raise typer.BadParameter(f"Invalid task ID: {arg1!r}") from None
    if not (arg1 and _KEY_RE.match(arg1)):
        raise typer.BadParameter(f"Expected a story key (e.g. KAN-5), got {arg1!r}")
    try:
        return arg1, int(arg2)
    except ValueError:
        raise typer.BadParameter(f"Invalid task ID: {arg2!r}") from None


def _split_story_and_text(arg1: Optional[str], arg2: Optional[str]) -> tuple[str, str]:
    if arg1 is None and arg2 is None:
        raise typer.BadParameter("Task title required.")
    if arg2 is None:
        if arg1 and _KEY_RE.match(arg1):
            raise typer.BadParameter("Task title required after story key.")
        return resolve_story_key(None), arg1 or ""
    if not (arg1 and _KEY_RE.match(arg1)):
        raise typer.BadParameter(f"Expected a story key, got {arg1!r}")
    return arg1, arg2


@app.command("list")
def task_list(
    story: Annotated[Optional[str], typer.Argument(help="Story key. Inferred from cwd if omitted.")] = None,
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


@app.command("add")
def task_add(
    arg1: Annotated[Optional[str], typer.Argument(help="Story key (optional) or task title.")] = None,
    arg2: Annotated[Optional[str], typer.Argument(help="Task title (when story key is given first).")] = None,
) -> None:
    """Append a new task to the story's task list. Created in Jira on push."""
    story_key, title = _split_story_and_text(arg1, arg2)
    if not title.strip():
        raise typer.BadParameter("Task title cannot be empty.")

    cfg = load_config()

    def add(tasks: list[dict]) -> None:
        next_id = (max((t["id"] for t in tasks), default=0)) + 1
        tasks.append({
            "id": next_id,
            "key": None,
            "title": title.strip(),
            "done": False,
            "status": "todo",
            "statusJira": cfg.status_map.get("todo"),
            "assignee": None,
            "_unpushed": True,
        })

    try:
        load_and_save_tasks(story_key, add)
    except WorkspaceMissingError as exc:
        err_console.print(f"[red]{exc}[/]")
        raise typer.Exit(code=1) from None
    console.print(f"[green]+[/] {story_key}: {title.strip()!r}  [dim](unpushed)[/]")


def _flip(story_key: str, task_id: int, *, done_value: bool) -> None:
    cfg = load_config()

    def mutate(tasks: list[dict]) -> None:
        for t in tasks:
            if t.get("id") == task_id:
                apply_status(t, "done" if done_value else "todo", cfg)
                return
        raise typer.BadParameter(f"No task with id {task_id} on {story_key}.")

    try:
        load_and_save_tasks(story_key, mutate)
    except WorkspaceMissingError as exc:
        err_console.print(f"[red]{exc}[/]")
        raise typer.Exit(code=1) from None


@app.command("done")
def task_done(
    arg1: Annotated[Optional[str], typer.Argument(help="Story key (optional) or task ID.")] = None,
    arg2: Annotated[Optional[str], typer.Argument(help="Task ID (when story key is given first).")] = None,
) -> None:
    """Mark a task complete by ID."""
    story_key, task_id = _split_story_id(arg1, arg2)
    _flip(story_key, task_id, done_value=True)
    console.print(f"[green]✓[/] {story_key} task {task_id} → done")


@app.command("undone")
def task_undone(
    arg1: Annotated[Optional[str], typer.Argument(help="Story key (optional) or task ID.")] = None,
    arg2: Annotated[Optional[str], typer.Argument(help="Task ID (when story key is given first).")] = None,
) -> None:
    """Mark a task incomplete by ID."""
    story_key, task_id = _split_story_id(arg1, arg2)
    _flip(story_key, task_id, done_value=False)
    console.print(f"[green]·[/] {story_key} task {task_id} → todo")


@app.command("edit")
def task_edit(
    arg1: Annotated[Optional[str], typer.Argument(help="Story key (optional) or task ID.")] = None,
    arg2: Annotated[Optional[str], typer.Argument(help="Task ID (when story key first) or new title.")] = None,
    title: Annotated[Optional[str], typer.Argument(help="New title (last positional).")] = None,
) -> None:
    """Edit a task's title by ID. Pass the new title or open $EDITOR if omitted."""
    if title is None and arg2 and not arg2.isdigit():
        story_key = resolve_story_key(None)
        try:
            task_id = int(arg1) if arg1 else None
        except ValueError:
            raise typer.BadParameter(f"Invalid task ID: {arg1!r}") from None
        new_title: Optional[str] = arg2
    elif title is None:
        story_key, task_id = _split_story_id(arg1, arg2)
        new_title = None
    else:
        story_key, task_id = _split_story_id(arg1, arg2)
        new_title = title

    if task_id is None:
        raise typer.BadParameter("Task ID required.")

    if new_title is None:
        try:
            tasks = load_tasks(story_key)
        except WorkspaceMissingError as exc:
            err_console.print(f"[red]{exc}[/]")
            raise typer.Exit(code=1) from None
        match = next((t for t in tasks if t.get("id") == task_id), None)
        if match is None:
            raise typer.BadParameter(f"No task with id {task_id} on {story_key}.")
        edited = open_editor(match.get("title", ""), suffix=".txt")
        if not edited:
            console.print("[dim]no changes[/]")
            return
        new_title = edited.strip().splitlines()[0] if edited.strip() else None

    if not new_title:
        raise typer.BadParameter("New title cannot be empty.")

    def mutate(tasks: list[dict]) -> None:
        for t in tasks:
            if t.get("id") == task_id:
                t["title"] = new_title
                return
        raise typer.BadParameter(f"No task with id {task_id} on {story_key}.")

    try:
        load_and_save_tasks(story_key, mutate)
    except WorkspaceMissingError as exc:
        err_console.print(f"[red]{exc}[/]")
        raise typer.Exit(code=1) from None
    console.print(f"[green]✓[/] {story_key} task {task_id} → {new_title!r}")


@app.command("delete")
def task_delete(
    arg1: Annotated[Optional[str], typer.Argument(help="Story key (optional) or task ID.")] = None,
    arg2: Annotated[Optional[str], typer.Argument(help="Task ID (when story key is given first).")] = None,
) -> None:
    """Remove a task by ID. Remaining tasks are re-numbered."""
    story_key, task_id = _split_story_id(arg1, arg2)

    def mutate(tasks: list[dict]) -> None:
        kept = [t for t in tasks if t.get("id") != task_id]
        if len(kept) == len(tasks):
            raise typer.BadParameter(f"No task with id {task_id} on {story_key}.")
        tasks.clear()
        tasks.extend(kept)
        renumber_tasks(tasks)

    try:
        load_and_save_tasks(story_key, mutate)
    except WorkspaceMissingError as exc:
        err_console.print(f"[red]{exc}[/]")
        raise typer.Exit(code=1) from None
    console.print(f"[red]-[/] {story_key} task {task_id} deleted")
