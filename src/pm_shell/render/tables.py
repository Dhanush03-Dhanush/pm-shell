from __future__ import annotations

from typing import Any

from rich.table import Table

from pm_shell.render.styles import style_priority, style_status, user_label


def epic_table(epics: list[dict[str, Any]], story_counts: dict[str, int]) -> Table:
    table = Table(show_header=True, header_style="bold", expand=False)
    table.add_column("KEY", style="cyan", no_wrap=True)
    table.add_column("SUMMARY")
    table.add_column("STATUS")
    table.add_column("PRIORITY")
    table.add_column("STORIES", justify="right")
    table.add_column("OWNER")
    for e in epics:
        table.add_row(
            e["key"],
            e.get("summary", ""),
            style_status(e.get("status"), e.get("statusJira")),
            style_priority(e.get("priority")),
            str(story_counts.get(e["key"], 0)),
            user_label(e.get("owner")),
        )
    return table


def story_table(stories: list[dict[str, Any]], task_counts: dict[str, tuple[int, int]]) -> Table:
    """task_counts: story_key → (done, total)."""
    table = Table(show_header=True, header_style="bold", expand=False)
    table.add_column("KEY", style="cyan", no_wrap=True)
    table.add_column("SUMMARY")
    table.add_column("STATUS")
    table.add_column("PRIORITY")
    table.add_column("EPIC", style="magenta", no_wrap=True)
    table.add_column("TASKS", justify="right")
    table.add_column("ASSIGNEE")
    for s in stories:
        done, total = task_counts.get(s["key"], (0, 0))
        tasks_label = f"{done}/{total}" if total else "—"
        table.add_row(
            s["key"],
            s.get("summary", ""),
            style_status(s.get("status"), s.get("statusJira")),
            style_priority(s.get("priority")),
            s.get("epic") or "—",
            tasks_label,
            user_label(s.get("assignee")),
        )
    return table


def task_table(tasks: list[dict[str, Any]]) -> Table:
    table = Table(show_header=True, header_style="bold", expand=False)
    table.add_column("#", justify="right", style="dim")
    table.add_column("KEY", style="cyan", no_wrap=True)
    table.add_column("✓", justify="center")
    table.add_column("TITLE")
    table.add_column("STATUS")
    table.add_column("ASSIGNEE")
    for t in tasks:
        check = "[green]✓[/green]" if t.get("done") else "[dim]·[/dim]"
        table.add_row(
            str(t.get("id", "")),
            t.get("key", ""),
            check,
            t.get("title", ""),
            style_status(t.get("status"), t.get("statusJira")),
            user_label(t.get("assignee")),
        )
    return table
