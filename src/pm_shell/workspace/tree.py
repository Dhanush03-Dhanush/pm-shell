from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator, Optional

from pm_shell.workspace.io import read_json
from pm_shell.workspace.paths import (
    epics_dir,
    find_epic_dir,
    find_story_dir,
    unparented_dir,
)


class WorkspaceMissingError(RuntimeError):
    """Raised when a requested epic/story isn't on disk."""


def iter_epic_dirs() -> Iterator[Path]:
    root = epics_dir()
    if not root.exists():
        return
    for child in sorted(root.iterdir()):
        if child.is_dir():
            yield child


def iter_story_dirs(epic_key: Optional[str] = None) -> Iterator[Path]:
    # No epic_key → walks every epic plus unparented/.
    if epic_key is not None:
        epic_dir = find_epic_dir(epic_key)
        if epic_dir is None:
            return
        for child in sorted(epic_dir.iterdir()):
            if child.is_dir():
                yield child
        return

    for epic_dir in iter_epic_dirs():
        for child in sorted(epic_dir.iterdir()):
            if child.is_dir():
                yield child
    orphans = unparented_dir()
    if orphans.exists():
        for child in sorted(orphans.iterdir()):
            if child.is_dir():
                yield child


def list_epics(*, include_deleted: bool = False) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for d in iter_epic_dirs():
        epic_path = d / "epic.json"
        if not epic_path.exists():
            continue
        record = read_json(epic_path)
        if not include_deleted and record.get("_deleted"):
            continue
        out.append(record)
    return out


def list_stories(
    epic_key: Optional[str] = None, *, include_deleted: bool = False
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for d in iter_story_dirs(epic_key):
        story_path = d / "story.json"
        if not story_path.exists():
            continue
        record = read_json(story_path)
        if not include_deleted and record.get("_deleted"):
            continue
        out.append(record)
    return out


def load_epic(key: str) -> dict[str, Any]:
    d = find_epic_dir(key)
    if d is None:
        raise WorkspaceMissingError(f"Epic {key} not found in workspace.")
    return read_json(d / "epic.json")


def load_story(key: str) -> dict[str, Any]:
    d = find_story_dir(key)
    if d is None:
        raise WorkspaceMissingError(f"Story {key} not found in workspace.")
    return read_json(d / "story.json")


def load_tasks(story_key: str) -> list[dict[str, Any]]:
    d = find_story_dir(story_key)
    if d is None:
        raise WorkspaceMissingError(f"Story {story_key} not found in workspace.")
    path = d / "tasks.json"
    if not path.exists():
        return []
    return read_json(path)


def load_comments(story_key: str) -> list[dict[str, Any]]:
    d = find_story_dir(story_key)
    if d is None:
        raise WorkspaceMissingError(f"Story {story_key} not found in workspace.")
    path = d / "comments.json"
    if not path.exists():
        return []
    return read_json(path)


def stories_for_epic(epic_key: str, *, include_deleted: bool = False) -> list[dict[str, Any]]:
    return list_stories(epic_key, include_deleted=include_deleted)
