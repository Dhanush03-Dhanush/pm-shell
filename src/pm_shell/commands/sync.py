"""Local-state sync commands: status, diff.

`status` summarises what's changed; `diff` shows the unified text diffs.
Both read from `sync/diff.py` and are pure local operations — no Jira calls.
"""

from __future__ import annotations

from typing import Annotated, Optional

import typer
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from pm_shell.io import console
from pm_shell.sync.diff import Change, compute_changes, format_diff_text

_KIND_STYLE = {
    "created": ("green", "+"),
    "modified": ("yellow", "~"),
    "deleted": ("red", "✗"),
}


def status() -> None:
    """Show all locally modified, added, or deleted items not yet pushed."""
    changes = compute_changes()
    if not changes:
        console.print("[dim]workspace is clean — nothing to push[/dim]")
        return

    table = Table(show_header=True, header_style="bold", expand=False, box=None, padding=(0, 1))
    table.add_column("", no_wrap=True)
    table.add_column("FILE", no_wrap=True)
    table.add_column("SUMMARY", overflow="fold")
    table.add_column("NOTES", style="dim")

    for c in sorted(changes, key=_change_sort_key):
        color, glyph = _KIND_STYLE.get(c.kind, ("white", "?"))
        glyph_text = Text(f"{glyph} {c.kind}", style=color)
        file_text = Text(c.file_label, style=_file_style(c.issue_type))
        notes = ", ".join(c.notes) if c.notes else ""
        table.add_row(glyph_text, file_text, c.summary, notes)

    console.print(table)
    console.print()
    _print_summary_line(changes)


def diff(
    key: Annotated[
        Optional[str],
        typer.Argument(help="Optional issue key to filter to a single item."),
    ] = None,
) -> None:
    """Print unified diffs for every changed file (or one item if KEY is given)."""
    changes = compute_changes()
    if key:
        changes = [c for c in changes if c.key == key]
    if not changes:
        console.print("[dim]no changes to show[/dim]")
        return

    for i, c in enumerate(changes):
        if i > 0:
            console.print()
        console.print(_header_for(c))
        console.print(format_diff_text(
            c.before_json, c.after_json,
            before_label=f"{c.file_label} (baseline)",
            after_label=f"{c.file_label} (current)",
        ))


# ── Helpers ─────────────────────────────────────────────────────────────────


def _print_summary_line(changes: list[Change]) -> None:
    by_kind: dict[str, int] = {}
    for c in changes:
        by_kind[c.kind] = by_kind.get(c.kind, 0) + 1
    parts = []
    for kind, n in by_kind.items():
        color, _ = _KIND_STYLE.get(kind, ("white", ""))
        parts.append(f"[{color}]{n} {kind}[/]")
    console.print(
        f"[dim]{len(changes)} change(s):[/] "
        + ", ".join(parts)
        + "  [dim]·  run `diff` to inspect, `push` (Phase 6) to apply.[/]"
    )


def _change_sort_key(c: Change) -> tuple[int, str, str]:
    type_order = {"epic": 0, "story": 1, "tasks": 2, "comments": 3}
    return (type_order.get(c.issue_type, 9), c.key, c.file_label)


def _file_style(issue_type: str) -> str:
    return {"epic": "cyan", "story": "magenta", "tasks": "green", "comments": "yellow"}.get(
        issue_type, "white"
    )


def _header_for(c: Change) -> Rule:
    color, _ = _KIND_STYLE.get(c.kind, ("white", "?"))
    title = f"[{color}]{c.kind}[/]  [bold]{c.file_label}[/]  [dim]{c.summary}[/]"
    return Rule(title=title, characters="─", style=color)
