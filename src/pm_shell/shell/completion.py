from __future__ import annotations

import shlex
from collections.abc import Iterable, Iterator
from typing import TYPE_CHECKING, Optional

import click
from prompt_toolkit.completion import (
    CompleteEvent,
    Completer,
    Completion,
    PathCompleter,
)
from prompt_toolkit.document import Document

from pm_shell.sync.aliases import CANONICAL_PRIORITIES, CANONICAL_STATUSES
from pm_shell.workspace.paths import baseline_dir, resolve_context

if TYPE_CHECKING:
    import typer

_BUILTINS = ("help", "exit", "quit", "cd", "pwd", "clear")
_NAV_COMMANDS = ("cd", "ls", "tree")
_PATH_LEADING = ("/", "~", ".")


class PMCompleter(Completer):
    def __init__(self, app: "typer.Typer") -> None:
        cmd = _get_root_command(app)
        self._top = sorted({*cmd.commands.keys(), *_BUILTINS})
        self._sub = {
            name: sorted(group.commands.keys())
            for name, group in cmd.commands.items()
            if isinstance(group, click.Group)
        }
        self._path_completer = PathCompleter(expanduser=True)
        self._all_keys_cache: Optional[list[str]] = None

    def _all_keys(self) -> list[str]:
        if self._all_keys_cache is None:
            root = baseline_dir()
            self._all_keys_cache = (
                sorted(p.stem for p in root.iterdir() if p.suffix == ".json")
                if root.exists()
                else []
            )
        return self._all_keys_cache

    def _scoped_nav_keys(self) -> list[str]:
        # Not cached — cwd may change between calls.
        from pm_shell.workspace.tree import list_epics, stories_for_epic
        epic_key, story_key = resolve_context()
        if story_key:
            return []
        if epic_key:
            return [s["key"] for s in stories_for_epic(epic_key)]
        return [e["key"] for e in list_epics()]

    def refresh_keys(self) -> None:
        self._all_keys_cache = None

    def get_completions(
        self, document: Document, complete_event: CompleteEvent
    ) -> Iterator[Completion]:
        text = document.text_before_cursor
        try:
            tokens = shlex.split(text) if text else []
        except ValueError:
            return

        partial = "" if (text and text[-1].isspace()) else (tokens[-1] if tokens else "")
        preceding = tokens[:-1] if (partial and tokens) else tokens

        if preceding and preceding[0] in _NAV_COMMANDS:
            if partial.startswith(_PATH_LEADING):
                sub_doc = Document(partial, len(partial))
                yield from self._path_completer.get_completions(sub_doc, complete_event)
            else:
                yield from _matches(self._scoped_nav_keys(), partial)
            return

        if preceding:
            last = preceding[-1]
            if last == "--status":
                yield from _matches(CANONICAL_STATUSES, partial)
                return
            if last == "--priority":
                yield from _matches(CANONICAL_PRIORITIES, partial)
                return

        if not preceding:
            yield from _matches(self._top, partial)
            return

        if len(preceding) == 1 and preceding[0] in self._sub:
            yield from _matches(self._sub[preceding[0]], partial)
            return

        yield from _matches(self._all_keys(), partial)


def _matches(candidates: Iterable[str], partial: str) -> Iterator[Completion]:
    needle = partial.lower()
    for candidate in candidates:
        if candidate.lower().startswith(needle):
            yield Completion(candidate, start_position=-len(partial))


def _get_root_command(app: "typer.Typer") -> click.Group:
    from typer.main import get_command

    cmd = get_command(app)
    assert isinstance(cmd, click.Group)
    return cmd
