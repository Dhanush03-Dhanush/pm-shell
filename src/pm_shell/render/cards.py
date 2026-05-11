from __future__ import annotations

from typing import Any, Optional

from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from pm_shell.render.adf import adf_to_plain
from pm_shell.render.styles import style_priority, style_status, user_label


def _kv_table(rows: list[tuple[str, str]]) -> Table:
    t = Table(show_header=False, box=None, padding=(0, 1, 0, 0))
    t.add_column(style="dim", no_wrap=True)
    t.add_column()
    for k, v in rows:
        t.add_row(k, v)
    return t


def _description_block(description: Any) -> Optional[Text]:
    body = adf_to_plain(description).strip()
    if not body:
        return None
    return Text(body)


def epic_card(epic: dict[str, Any], stories: list[dict[str, Any]]) -> Panel:
    rows = [
        ("Status", style_status(epic.get("status"), epic.get("statusJira"))),
        ("Priority", style_priority(epic.get("priority"))),
        ("Owner", user_label(epic.get("owner"))),
        ("Labels", ", ".join(epic.get("labels") or []) or "[dim]—[/dim]"),
        ("Created", epic.get("created") or "—"),
        ("Updated", epic.get("updated") or "—"),
    ]
    blocks: list[Any] = [_kv_table(rows)]

    desc = _description_block(epic.get("description"))
    if desc is not None:
        blocks.append(Text(""))
        blocks.append(Text("Description", style="dim"))
        blocks.append(desc)

    if stories:
        blocks.append(Text(""))
        blocks.append(Text(f"Stories ({len(stories)})", style="dim"))
        sub = Table(show_header=False, box=None, padding=(0, 1, 0, 0))
        sub.add_column(style="cyan", no_wrap=True)
        sub.add_column()
        sub.add_column()
        for s in stories:
            sub.add_row(
                s.get("key", ""),
                s.get("summary", ""),
                style_status(s.get("status"), s.get("statusJira")),
            )
        blocks.append(sub)

    title = f"[bold]{epic.get('key', '?')}[/bold]  {epic.get('summary', '')}"
    return Panel(Group(*blocks), title=title, title_align="left", border_style="cyan")


def story_card(
    story: dict[str, Any],
    tasks: list[dict[str, Any]],
    latest_comment: Optional[dict[str, Any]] = None,
) -> Panel:
    done = sum(1 for t in tasks if t.get("done"))
    tasks_summary = f"{done}/{len(tasks)} done" if tasks else "no tasks"

    rows = [
        ("Status", style_status(story.get("status"), story.get("statusJira"))),
        ("Priority", style_priority(story.get("priority"))),
        ("Assignee", user_label(story.get("assignee"))),
        ("Epic", story.get("epic") or "[dim]—[/dim]"),
        ("Labels", ", ".join(story.get("labels") or []) or "[dim]—[/dim]"),
        ("Tasks", tasks_summary),
        ("Created", story.get("created") or "—"),
        ("Updated", story.get("updated") or "—"),
    ]
    blocks: list[Any] = [_kv_table(rows)]

    desc = _description_block(story.get("description"))
    if desc is not None:
        blocks.append(Text(""))
        blocks.append(Text("Description", style="dim"))
        blocks.append(desc)

    if tasks:
        blocks.append(Text(""))
        blocks.append(Text("Tasks", style="dim"))
        sub = Table(show_header=False, box=None, padding=(0, 1, 0, 0))
        sub.add_column(justify="right", style="dim", no_wrap=True)
        sub.add_column(no_wrap=True)
        sub.add_column()
        sub.add_column(style="green", no_wrap=True)
        for t in tasks:
            check = "[green]✓[/green]" if t.get("done") else "[dim]·[/dim]"
            sub.add_row(
                str(t.get("id", "")),
                check,
                t.get("title", ""),
                t.get("key", "") or "",
            )
        blocks.append(sub)

    if latest_comment:
        blocks.append(Text(""))
        author = user_label(latest_comment.get("author"))
        when = latest_comment.get("created") or ""
        blocks.append(Text(f"Latest comment — {author}  {when}", style="dim"))
        body = adf_to_plain(latest_comment.get("body")).strip()
        if body:
            blocks.append(Text(body))

    title = f"[bold]{story.get('key', '?')}[/bold]  {story.get('summary', '')}"
    return Panel(Group(*blocks), title=title, title_align="left", border_style="magenta")
