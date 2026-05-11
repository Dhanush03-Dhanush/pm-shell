from __future__ import annotations

import re
from typing import Annotated, Optional

import typer

from pm_shell.commands._context import resolve_story_key
from pm_shell.commands._editor import open_editor
from pm_shell.commands._mutate import (
    append_comment,
    apply_status,
    load_and_save_story,
    next_local_key,
)
from pm_shell.config import load_config
from pm_shell.io import console, err_console
from pm_shell.render.adf import adf_to_plain, plain_to_adf
from pm_shell.render.cards import story_card
from pm_shell.render.tables import story_table
from pm_shell.sync.aliases import canonicalize_priority, canonicalize_status
from pm_shell.workspace.io import atomic_write_json
from pm_shell.workspace.paths import (
    find_epic_dir,
    issue_dirname,
    resolve_context,
    unparented_dir,
)
from pm_shell.workspace.tree import (
    WorkspaceMissingError,
    list_stories,
    load_story,
    load_tasks,
    load_comments,
)

app = typer.Typer(help="Story operations.", no_args_is_help=True)


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


def _set_fields(
    record: dict,
    *,
    status: Optional[str],
    priority: Optional[str],
    summary: Optional[str],
    assignee: Optional[str],
    add_labels: list[str],
    description: Optional[str],
    epic: Optional[str],
    points: Optional[int],
) -> list[str]:
    """Mutate `record` in place. Returns a list of human-readable change descriptions."""
    cfg = load_config()
    changes: list[str] = []

    if status is not None:
        canonical = canonicalize_status(status)
        apply_status(record, canonical, cfg)
        changes.append(f"status → {canonical} ({record['statusJira']})")

    if priority is not None:
        record["priority"] = canonicalize_priority(priority)
        changes.append(f"priority → {record['priority']}")

    if summary is not None:
        record["summary"] = summary
        changes.append(f"summary → {summary!r}")

    if assignee is not None:
        if assignee == "":
            record["assignee"] = None
            changes.append("assignee cleared")
        else:
            record["assignee"] = {"accountId": None, "displayName": None, "email": assignee}
            changes.append(f"assignee → {assignee}")

    if add_labels:
        existing = record.get("labels") or []
        merged = list(dict.fromkeys([*existing, *add_labels]))
        record["labels"] = merged
        changes.append(f"labels += {add_labels}")

    if description is not None:
        record["description"] = plain_to_adf(description)
        changes.append("description updated")

    if epic is not None:
        record["epic"] = epic or None
        changes.append(f"epic → {epic or 'cleared'}")

    if points is not None:
        record["points"] = points
        changes.append(f"points → {points}")

    return changes


@app.command("set")
def story_set(
    key: Annotated[Optional[str], typer.Argument(help="Story key. Inferred from cwd if omitted.")] = None,
    status: Annotated[Optional[str], typer.Option("--status", help="todo | in-progress | done | blocked (aliases accepted).")] = None,
    priority: Annotated[Optional[str], typer.Option("--priority", help="low | medium | high | critical.")] = None,
    summary: Annotated[Optional[str], typer.Option("--summary", help="New title.")] = None,
    assignee: Annotated[Optional[str], typer.Option("--assignee", help="User email. Pass empty string to clear.")] = None,
    label: Annotated[Optional[list[str]], typer.Option("--label", help="Add a label. Repeatable.")] = None,
    description: Annotated[Optional[str], typer.Option("--description", help="Inline description (use `pm story edit` for multi-line).")] = None,
    epic: Annotated[Optional[str], typer.Option("--epic", help="Reparent to a different epic key.")] = None,
    points: Annotated[Optional[int], typer.Option("--points", help="Story points (integer).")] = None,
) -> None:
    """Update one or more fields on a story inline."""
    resolved = resolve_story_key(key)
    try:
        record = load_and_save_story(
            resolved,
            lambda r: _set_fields(
                r,
                status=status, priority=priority, summary=summary,
                assignee=assignee, add_labels=label or [],
                description=description, epic=epic, points=points,
            ),
        )
    except WorkspaceMissingError as exc:
        err_console.print(f"[red]{exc}[/]")
        raise typer.Exit(code=1) from None

    console.print(f"[green]✓[/] {resolved} updated")


@app.command("start")
def story_start(
    key: Annotated[Optional[str], typer.Argument(help="Story key. Inferred from cwd if omitted.")] = None,
) -> None:
    """Shorthand: set status to in-progress."""
    resolved = resolve_story_key(key)
    cfg = load_config()
    load_and_save_story(resolved, lambda r: apply_status(r, "in-progress", cfg))
    console.print(f"[green]✓[/] {resolved} → in-progress")


@app.command("done")
def story_done(
    key: Annotated[Optional[str], typer.Argument(help="Story key. Inferred from cwd if omitted.")] = None,
) -> None:
    """Shorthand: set status to done. Warns if incomplete tasks remain."""
    resolved = resolve_story_key(key)
    try:
        tasks = load_tasks(resolved)
    except WorkspaceMissingError as exc:
        err_console.print(f"[red]{exc}[/]")
        raise typer.Exit(code=1) from None
    incomplete = [t for t in tasks if not t.get("done")]
    if incomplete:
        console.print(
            f"[yellow]warning:[/] {len(incomplete)} of {len(tasks)} tasks still open "
            f"on {resolved}."
        )
    cfg = load_config()
    load_and_save_story(resolved, lambda r: apply_status(r, "done", cfg))
    console.print(f"[green]✓[/] {resolved} → done")


_KEY_RE = re.compile(r"^[A-Z][A-Z0-9]*-\d+$")


@app.command("block")
def story_block(
    arg1: Annotated[Optional[str], typer.Argument(help="Story key (optional) or reason.")] = None,
    arg2: Annotated[Optional[str], typer.Argument(help="Reason (when story key is given first).")] = None,
) -> None:
    """Shorthand: set status to blocked. Optional reason is appended as a comment."""
    if arg1 is None:
        resolved = resolve_story_key(None)
        reason: Optional[str] = None
    elif arg2 is None:
        if _KEY_RE.match(arg1):
            resolved = arg1
            reason = None
        else:
            resolved = resolve_story_key(None)
            reason = arg1
    else:
        if not _KEY_RE.match(arg1):
            raise typer.BadParameter(f"Expected a story key, got {arg1!r}")
        resolved = arg1
        reason = arg2

    cfg = load_config()
    load_and_save_story(resolved, lambda r: apply_status(r, "blocked", cfg))
    msg = f"[green]✓[/] {resolved} → blocked"
    if reason:
        append_comment(resolved, f"Blocked: {reason}", cfg=cfg)
        msg += " (comment queued)"
    console.print(msg)


@app.command("edit")
def story_edit(
    key: Annotated[Optional[str], typer.Argument(help="Story key. Inferred from cwd if omitted.")] = None,
) -> None:
    """Open the story description in $EDITOR."""
    resolved = resolve_story_key(key)
    try:
        story = load_story(resolved)
    except WorkspaceMissingError as exc:
        err_console.print(f"[red]{exc}[/]")
        raise typer.Exit(code=1) from None
    initial = adf_to_plain(story.get("description"))
    new_text = open_editor(initial, suffix=".md")
    if new_text is None:
        console.print("[dim]no changes[/]")
        return
    load_and_save_story(resolved, lambda r: r.update({"description": plain_to_adf(new_text)}))
    console.print(f"[green]✓[/] {resolved} description updated")


@app.command("delete")
def story_delete(
    key: Annotated[Optional[str], typer.Argument(help="Story key. Inferred from cwd if omitted.")] = None,
) -> None:
    """Mark a story for deletion. Executed on next `push`.

    Unpushed (NEW-*) stories are removed immediately since they don't exist in Jira yet.
    """
    import shutil

    from pm_shell.workspace.paths import find_story_dir

    resolved = resolve_story_key(key)
    try:
        story = load_story(resolved)
    except WorkspaceMissingError as exc:
        err_console.print(f"[red]{exc}[/]")
        raise typer.Exit(code=1) from None

    sdir = find_story_dir(resolved)
    if story.get("_unpushed") and sdir is not None:
        shutil.rmtree(sdir)
        console.print(f"[red]-[/] {resolved} removed (was unpushed)")
        return

    load_and_save_story(resolved, lambda r: r.update({"_deleted": True}))
    console.print(f"[red]✗[/] {resolved} marked for deletion  [dim](run `push` to apply)[/]")


@app.command("undelete")
def story_undelete(
    key: Annotated[Optional[str], typer.Argument(help="Story key. Inferred from cwd if omitted.")] = None,
) -> None:
    """Clear the deletion mark on a story."""
    resolved = resolve_story_key(key)
    try:
        load_and_save_story(resolved, lambda r: r.pop("_deleted", None))
    except WorkspaceMissingError as exc:
        err_console.print(f"[red]{exc}[/]")
        raise typer.Exit(code=1) from None
    console.print(f"[green]✓[/] {resolved} restored")


@app.command("create")
def story_create(
    summary: Annotated[str, typer.Argument(help="Story title.")],
    epic: Annotated[Optional[str], typer.Option("--epic", "-e", help="Parent epic key. Inferred from cwd if inside an epic dir.")] = None,
    priority: Annotated[Optional[str], typer.Option("--priority")] = None,
    assignee: Annotated[Optional[str], typer.Option("--assignee", help="User email.")] = None,
    label: Annotated[Optional[list[str]], typer.Option("--label", help="Add a label. Repeatable.")] = None,
    description: Annotated[Optional[str], typer.Option("--description")] = None,
    points: Annotated[Optional[int], typer.Option("--points", help="Story points (integer).")] = None,
) -> None:
    """Create a new story locally. The Jira issue is created on `pm push`."""
    if not summary.strip():
        raise typer.BadParameter("Story summary cannot be empty.")

    if epic is None:
        cwd_epic, _ = resolve_context()
        epic = cwd_epic

    epic_dir = find_epic_dir(epic) if epic else None
    if epic and epic_dir is None:
        raise typer.BadParameter(f"Epic {epic} not found in workspace.")

    cfg = load_config()
    new_key = next_local_key(cfg)

    record = {
        "key": new_key,
        "issueType": "Story",
        "summary": summary.strip(),
        "status": "todo",
        "statusJira": cfg.status_map.get("todo"),
        "priority": canonicalize_priority(priority) if priority else None,
        "assignee": {"accountId": None, "displayName": None, "email": assignee} if assignee else None,
        "labels": label or [],
        "epic": epic,
        "points": points,
        "description": plain_to_adf(description) if description else None,
        "_unpushed": True,
    }

    if epic_dir is not None:
        container = epic_dir
    else:
        container = unparented_dir()
        container.mkdir(parents=True, exist_ok=True)

    sdir = container / issue_dirname(new_key, summary)
    try:
        sdir.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        err_console.print(f"[red]error:[/] directory already exists: {sdir}")
        raise typer.Exit(code=1) from None
    atomic_write_json(sdir / "story.json", record)
    atomic_write_json(sdir / "tasks.json", [])
    atomic_write_json(sdir / "comments.json", [])

    epic_hint = f" under [cyan]{epic}[/]" if epic else " [yellow](no epic)[/]"
    console.print(
        f"[green]+[/] [magenta bold]{new_key}[/]: {summary.strip()}{epic_hint}  "
        f"[dim](unpushed — run `push` to create in Jira)[/]"
    )
