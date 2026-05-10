from __future__ import annotations

from typing import Annotated, Optional

import typer
from rich.console import Console

from pm_shell.commands._context import resolve_epic_key
from pm_shell.commands._editor import open_editor
from pm_shell.commands._mutate import apply_status, load_and_save_epic
from pm_shell.config import load_config
from pm_shell.render.adf import adf_to_plain, plain_to_adf
from pm_shell.render.cards import epic_card
from pm_shell.render.tables import epic_table
from pm_shell.sync.aliases import canonicalize_priority, canonicalize_status
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
