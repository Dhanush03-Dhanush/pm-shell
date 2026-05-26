from __future__ import annotations

from typing import Annotated, Optional

import typer

from pm_shell.commands._context import resolve_epic_key
from pm_shell.commands._editor import open_editor
from pm_shell.commands._mutate import (
    apply_status,
    load_and_save_epic,
    next_local_key,
)
from pm_shell.config import load_config
from pm_shell.io import console, err_console
from pm_shell.render.adf import adf_to_plain, plain_to_adf
from pm_shell.render.cards import epic_card
from pm_shell.render.tables import epic_table
from pm_shell.sync.aliases import canonicalize_priority, canonicalize_status
from pm_shell.workspace.io import atomic_write_json
from pm_shell.workspace.paths import epics_dir, issue_dirname
from pm_shell.workspace.tree import (
    WorkspaceMissingError,
    list_epics,
    load_epic,
    stories_for_epic,
)

app = typer.Typer(help="Epic operations.", no_args_is_help=True)


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


def _set_epic_fields(
    record: dict,
    *,
    status: Optional[str],
    priority: Optional[str],
    summary: Optional[str],
    owner: Optional[str],
    add_labels: list[str],
    description: Optional[str],
) -> None:
    cfg = load_config()
    if status is not None:
        apply_status(record, canonicalize_status(status), cfg)
    if priority is not None:
        record["priority"] = canonicalize_priority(priority)
    if summary is not None:
        record["summary"] = summary
    if owner is not None:
        if owner == "":
            record["owner"] = None
        else:
            record["owner"] = {"accountId": None, "displayName": None, "email": owner}
    if add_labels:
        existing = record.get("labels") or []
        record["labels"] = list(dict.fromkeys([*existing, *add_labels]))
    if description is not None:
        record["description"] = plain_to_adf(description)


@app.command("set")
def epic_set(
    key: Annotated[Optional[str], typer.Argument(help="Epic key. Inferred from cwd if omitted.")] = None,
    status: Annotated[Optional[str], typer.Option("--status")] = None,
    priority: Annotated[Optional[str], typer.Option("--priority")] = None,
    summary: Annotated[Optional[str], typer.Option("--summary")] = None,
    owner: Annotated[Optional[str], typer.Option("--owner", help="User email. Pass empty string to clear.")] = None,
    label: Annotated[Optional[list[str]], typer.Option("--label", help="Add a label. Repeatable.")] = None,
    description: Annotated[Optional[str], typer.Option("--description")] = None,
) -> None:
    """Update one or more fields on an epic inline."""
    resolved = resolve_epic_key(key)
    try:
        load_and_save_epic(
            resolved,
            lambda r: _set_epic_fields(
                r,
                status=status, priority=priority, summary=summary,
                owner=owner, add_labels=label or [], description=description,
            ),
        )
    except WorkspaceMissingError as exc:
        err_console.print(f"[red]{exc}[/]")
        raise typer.Exit(code=1) from None
    console.print(f"[green]✓[/] {resolved} updated")


@app.command("create")
def epic_create(
    summary: Annotated[str, typer.Argument(help="Epic title.")],
    priority: Annotated[Optional[str], typer.Option("--priority", help="low | medium | high | critical")] = None,
    owner: Annotated[Optional[str], typer.Option("--owner", help="User email.")] = None,
    label: Annotated[Optional[list[str]], typer.Option("--label", help="Add a label. Repeatable.")] = None,
    description: Annotated[Optional[str], typer.Option("--description")] = None,
) -> None:
    """Create a new epic locally. The Jira issue is created on `pm push`."""
    if not summary.strip():
        raise typer.BadParameter("Epic summary cannot be empty.")

    cfg = load_config()
    new_key = next_local_key(cfg)

    record = {
        "key": new_key,
        "issueType": "Epic",
        "summary": summary.strip(),
        "status": "todo",
        "statusJira": cfg.status_map.get("todo"),
        "priority": canonicalize_priority(priority) if priority else None,
        "owner": {"accountId": None, "displayName": None, "email": owner} if owner else None,
        "labels": label or [],
        "description": plain_to_adf(description) if description else None,
        "_unpushed": True,
    }

    edir = epics_dir() / issue_dirname(new_key, summary)
    try:
        edir.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        err_console.print(f"[red]error:[/] directory already exists: {edir}")
        raise typer.Exit(code=1) from None
    atomic_write_json(edir / "epic.json", record)

    console.print(
        f"[green]+[/] [cyan bold]{new_key}[/]: {summary.strip()}  "
        f"[dim](unpushed — run `push` to create in Jira)[/]"
    )


@app.command("delete")
def epic_delete(
    key: Annotated[Optional[str], typer.Argument(help="Epic key. Inferred from cwd if omitted.")] = None,
) -> None:
    """Mark an epic and its child stories for deletion (applied on next `push`).
    Unpushed (NEW-*) epics are removed immediately."""
    import shutil

    from pm_shell.commands._mutate import load_and_save_story
    from pm_shell.workspace.paths import find_epic_dir
    from pm_shell.workspace.tree import stories_for_epic

    resolved = resolve_epic_key(key)
    try:
        epic = load_epic(resolved)
    except WorkspaceMissingError as exc:
        err_console.print(f"[red]{exc}[/]")
        raise typer.Exit(code=1) from None

    edir = find_epic_dir(resolved)
    if epic.get("_unpushed") and edir is not None:
        shutil.rmtree(edir)
        console.print(f"[red]-[/] {resolved} removed (was unpushed)")
        return

    cascaded = 0
    for s in stories_for_epic(resolved, include_deleted=True):
        if s.get("_deleted"):
            continue
        load_and_save_story(s["key"], lambda r: r.update({"_deleted": True}))
        cascaded += 1

    load_and_save_epic(resolved, lambda r: r.update({"_deleted": True}))
    suffix = f" (+ {cascaded} child story/stories)" if cascaded else ""
    console.print(f"[red]✗[/] {resolved} marked for deletion{suffix}  [dim](run `push` to apply)[/]")


@app.command("undelete")
def epic_undelete(
    key: Annotated[Optional[str], typer.Argument(help="Epic key. Inferred from cwd if omitted.")] = None,
    stories: Annotated[
        bool, typer.Option("--stories/--no-stories", help="Also undelete child stories.")
    ] = True,
) -> None:
    """Clear the deletion mark on an epic (and optionally its child stories)."""
    from pm_shell.commands._mutate import load_and_save_story
    from pm_shell.workspace.tree import stories_for_epic

    resolved = resolve_epic_key(key)
    try:
        load_and_save_epic(resolved, lambda r: r.pop("_deleted", None))
    except WorkspaceMissingError as exc:
        err_console.print(f"[red]{exc}[/]")
        raise typer.Exit(code=1) from None

    restored = 0
    if stories:
        for s in stories_for_epic(resolved, include_deleted=True):
            if s.get("_deleted"):
                load_and_save_story(s["key"], lambda r: r.pop("_deleted", None))
                restored += 1

    suffix = f" (+ {restored} child story/stories restored)" if restored else ""
    console.print(f"[green]✓[/] {resolved} restored{suffix}")


@app.command("edit")
def epic_edit(
    key: Annotated[Optional[str], typer.Argument(help="Epic key. Inferred from cwd if omitted.")] = None,
) -> None:
    """Open the epic description in $EDITOR."""
    resolved = resolve_epic_key(key)
    try:
        epic = load_epic(resolved)
    except WorkspaceMissingError as exc:
        err_console.print(f"[red]{exc}[/]")
        raise typer.Exit(code=1) from None
    initial = adf_to_plain(epic.get("description"))
    new_text = open_editor(initial, suffix=".md")
    if new_text is None:
        console.print("[dim]no changes[/]")
        return
    load_and_save_epic(resolved, lambda r: r.update({"description": plain_to_adf(new_text)}))
    console.print(f"[green]✓[/] {resolved} description updated")
