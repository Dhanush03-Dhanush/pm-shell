"""Yes/No confirmation modal — used by `merge` before applying to Jira."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Center, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class ConfirmScreen(ModalScreen[bool]):
    """Modal that resolves to True (confirmed) or False (cancelled).

    Use via `app.push_screen(ConfirmScreen(...), callback)`. The callback receives
    the bool result and runs in the App's event loop after the modal is dismissed.
    """

    CSS_PATH = "confirm_screen.tcss"

    BINDINGS = [
        Binding("escape", "dismiss(False)", "cancel", show=True),
        Binding("n", "dismiss(False)", "no", show=False),
        Binding("y", "dismiss(True)", "yes", show=True),
        Binding("enter", "dismiss(True)", "confirm", show=False),
    ]

    def __init__(self, title: str, body: Text, *, confirm_label: str = "Yes", cancel_label: str = "No"):
        super().__init__()
        self._title = title
        self._body = body
        self._confirm_label = confirm_label
        self._cancel_label = cancel_label

    def compose(self) -> ComposeResult:
        with Center():
            with Vertical(id="confirm-box"):
                yield Static(self._title, id="confirm-title")
                yield Static(self._body, id="confirm-body")
                with Center(id="confirm-buttons"):
                    yield Button(self._confirm_label, id="confirm-yes", variant="warning")
                    yield Button(self._cancel_label, id="confirm-no", variant="default")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm-yes")

    def action_dismiss(self, value: bool) -> None:
        self.dismiss(value)


__all__ = ["ConfirmScreen"]
