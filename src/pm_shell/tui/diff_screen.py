"""Diff viewer modal — file list on the left, unified diff on the right.

Push onto the app stack with `app.push_screen(DiffScreen(compute_changes()))`.
Esc pops back to the main shell. ↑/↓ (or j/k) cycle through changed files;
the right pane re-renders for the highlighted entry.
"""

from __future__ import annotations

from typing import Optional

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Footer, Label, ListItem, ListView, RichLog, Static

from pm_shell.sync.diff import Change, format_diff_text

_KIND_STYLE = {
    "created": "green",
    "modified": "yellow",
    "deleted": "red",
}
_KIND_GLYPH = {
    "created": "+",
    "modified": "~",
    "deleted": "✗",
}
_TYPE_STYLE = {
    "epic": "cyan",
    "story": "magenta",
    "tasks": "green",
    "comments": "yellow",
}


class DiffScreen(Screen):
    """Modal: file list + diff pane. Esc returns to the main app."""

    CSS_PATH = "diff_screen.tcss"

    BINDINGS = [
        Binding("escape", "app.pop_screen", "back", show=True),
        Binding("q", "app.pop_screen", "back", show=False),
        Binding("j", "list_down", "next", show=False),
        Binding("k", "list_up", "prev", show=False),
        Binding("pageup", "scroll_diff_up", "scroll", show=True),
        Binding("pagedown", "scroll_diff_down", "", show=False),
    ]

    def __init__(self, changes: list[Change]) -> None:
        super().__init__()
        self._changes = changes

    def compose(self) -> ComposeResult:
        yield Static(self._header_text(), id="diff-header")
        with Horizontal(id="diff-body"):
            yield ListView(id="diff-files")
            yield RichLog(
                id="diff-view",
                wrap=False,
                markup=False,
                highlight=False,
                auto_scroll=False,
            )
        yield Footer()

    def on_mount(self) -> None:
        files = self.query_one("#diff-files", ListView)
        for change in self._changes:
            files.append(ListItem(Label(self._format_file_row(change))))
        files.focus()
        if self._changes:
            files.index = 0
            self._render_change(self._changes[0])

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        idx = event.list_view.index
        if idx is None or idx >= len(self._changes):
            return
        self._render_change(self._changes[idx])

    # ── rendering ────────────────────────────────────────────────────────────

    def _header_text(self) -> Text:
        if not self._changes:
            return Text("No changes", style="dim")
        counts: dict[str, int] = {}
        for c in self._changes:
            counts[c.kind] = counts.get(c.kind, 0) + 1
        parts = [
            f"[{_KIND_STYLE.get(k, 'white')}]{n} {k}[/]" for k, n in counts.items()
        ]
        return Text.from_markup(
            f"[bold]Diff[/]  ·  {len(self._changes)} change(s):  " + ", ".join(parts)
            + "    [dim]Esc to return[/]"
        )

    def _format_file_row(self, c: Change) -> Text:
        glyph = _KIND_GLYPH.get(c.kind, "·")
        kind_color = _KIND_STYLE.get(c.kind, "white")
        type_color = _TYPE_STYLE.get(c.issue_type, "white")
        return Text.from_markup(
            f"[{kind_color}]{glyph}[/] [{type_color}]{c.file_label}[/]"
        )

    def _render_change(self, change: Change) -> None:
        view = self.query_one("#diff-view", RichLog)
        view.clear()
        view.write(self._diff_title(change))
        if change.notes:
            view.write(Text("  " + " · ".join(change.notes), style="dim"))
        view.write(Text(""))
        view.write(format_diff_text(
            change.before_json,
            change.after_json,
            before_label=f"{change.file_label} (baseline)",
            after_label=f"{change.file_label} (current)",
        ))

    def _diff_title(self, c: Change) -> Text:
        kind_color = _KIND_STYLE.get(c.kind, "white")
        type_color = _TYPE_STYLE.get(c.issue_type, "white")
        return Text.from_markup(
            f"[{kind_color} bold]{c.kind}[/]  "
            f"[{type_color} bold]{c.file_label}[/]  "
            f"[dim]{c.summary}[/]"
        )

    # ── actions ──────────────────────────────────────────────────────────────

    def action_list_down(self) -> None:
        files = self.query_one("#diff-files", ListView)
        files.action_cursor_down()

    def action_list_up(self) -> None:
        files = self.query_one("#diff-files", ListView)
        files.action_cursor_up()

    def action_scroll_diff_up(self) -> None:
        self.query_one("#diff-view", RichLog).scroll_page_up(animate=False)

    def action_scroll_diff_down(self) -> None:
        self.query_one("#diff-view", RichLog).scroll_page_down(animate=False)


def diff_screen(changes: Optional[list[Change]] = None) -> DiffScreen:
    """Convenience constructor used by the TUI submit-handler."""
    from pm_shell.sync.diff import compute_changes
    return DiffScreen(changes if changes is not None else compute_changes())
