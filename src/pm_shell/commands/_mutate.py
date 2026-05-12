"""Shared helpers for local-write commands (Phase 4 mutations)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import typer

from pm_shell.config import Config, load_config
from pm_shell.render.adf import plain_to_adf
from pm_shell.workspace.io import atomic_write_json, read_json
from pm_shell.workspace.paths import find_epic_dir, find_story_dir
from pm_shell.workspace.tree import WorkspaceMissingError


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def next_local_key(cfg: Config) -> str:
    """Reserve and return the next `NEW-<n>` placeholder key.

    Increments and persists `cfg.next_local_id`. Push (Phase 6) replaces these
    with real Jira keys after the issue is created server-side.
    """
    from pm_shell.config import save_config
    n = cfg.next_local_id
    cfg.next_local_id = n + 1
    save_config(cfg)
    return f"NEW-{n}"


def jira_status_for(canonical: str, cfg: Config) -> str:
    """Translate canonical status → Jira display name via config.statusMap.

    Errors clearly if the workflow has no mapped status (typical for `blocked`).
    """
    mapped = cfg.status_map.get(canonical)
    if not mapped:
        available = ", ".join(k for k, v in cfg.status_map.items() if v) or "(none)"
        raise typer.BadParameter(
            f"Status '{canonical}' is not mapped to a Jira status in this workflow. "
            f"Mapped statuses: {available}. Edit .jira/config.json statusMap to add it."
        )
    return mapped


def story_path(key: str) -> Path:
    d = find_story_dir(key)
    if d is None:
        raise WorkspaceMissingError(f"Story {key} not found in workspace.")
    return d / "story.json"


def tasks_path(key: str) -> Path:
    d = find_story_dir(key)
    if d is None:
        raise WorkspaceMissingError(f"Story {key} not found in workspace.")
    return d / "tasks.json"


def comments_path(key: str) -> Path:
    d = find_story_dir(key)
    if d is None:
        raise WorkspaceMissingError(f"Story {key} not found in workspace.")
    return d / "comments.json"


def epic_path(key: str) -> Path:
    d = find_epic_dir(key)
    if d is None:
        raise WorkspaceMissingError(f"Epic {key} not found in workspace.")
    return d / "epic.json"


def load_and_save_story(key: str, mutator) -> dict[str, Any]:
    path = story_path(key)
    data = read_json(path)
    mutator(data)
    atomic_write_json(path, data)
    return data


def load_and_save_epic(key: str, mutator) -> dict[str, Any]:
    path = epic_path(key)
    data = read_json(path)
    mutator(data)
    atomic_write_json(path, data)
    return data


def load_and_save_tasks(story_key: str, mutator) -> list[dict[str, Any]]:
    path = tasks_path(story_key)
    data: list[dict[str, Any]] = read_json(path) if path.exists() else []
    mutator(data)
    atomic_write_json(path, data)
    return data


def append_comment(story_key: str, body_text: str, *, cfg: Optional[Config] = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    path = comments_path(story_key)
    comments: list[dict[str, Any]] = read_json(path) if path.exists() else []
    now = now_iso()
    record = {
        "id": f"local-{uuid.uuid4().hex[:12]}",
        "author": {"accountId": None, "displayName": None, "email": cfg.email},
        "body": plain_to_adf(body_text),
        "created": now,
        "updated": now,
        "_unpushed": True,
    }
    comments.append(record)
    atomic_write_json(path, comments)
    return record


def apply_status(record: dict[str, Any], canonical: str, cfg: Config) -> None:
    """Set canonical + Jira status fields on a story/epic/task record."""
    record["status"] = canonical
    record["statusJira"] = jira_status_for(canonical, cfg)
    if "done" in record:
        record["done"] = canonical == "done"


def renumber_tasks(tasks: list[dict[str, Any]]) -> None:
    for i, t in enumerate(tasks, start=1):
        t["id"] = i
