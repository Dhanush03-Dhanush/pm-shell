from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Optional

from pm_shell.config import workspace_dir

_SLUG_STRIP_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str, *, max_length: int = 60) -> str:
    """Lowercased, ASCII-folded, hyphen-separated slug. Empty input yields 'untitled'."""
    if not text:
        return "untitled"
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    slug = _SLUG_STRIP_RE.sub("-", normalized.lower()).strip("-")
    if not slug:
        return "untitled"
    return slug[:max_length].rstrip("-") or "untitled"


def issue_dirname(key: str, summary: str) -> str:
    return f"{key}_{slugify(summary)}"


def epics_dir() -> Path:
    return workspace_dir() / "epics"


def unparented_dir() -> Path:
    return workspace_dir() / "unparented"


def baseline_dir() -> Path:
    return workspace_dir() / ".baseline"


def log_dir() -> Path:
    return workspace_dir() / ".log"


def parse_key_from_dirname(name: str) -> Optional[str]:
    """`KAN-4_auth-overhaul` → `KAN-4`. Returns None if the name has no underscore."""
    if "_" not in name:
        return None
    return name.split("_", 1)[0]


def find_epic_dir(key: str) -> Optional[Path]:
    root = epics_dir()
    if not root.exists():
        return None
    for child in root.iterdir():
        if child.is_dir() and parse_key_from_dirname(child.name) == key:
            return child
    return None


def find_story_dir(key: str) -> Optional[Path]:
    """Walk epic dirs and unparented/ to locate a story by key."""
    root = epics_dir()
    if root.exists():
        for epic_dir in root.iterdir():
            if not epic_dir.is_dir():
                continue
            for story_dir in epic_dir.iterdir():
                if story_dir.is_dir() and parse_key_from_dirname(story_dir.name) == key:
                    return story_dir
    orphans = unparented_dir()
    if orphans.exists():
        for story_dir in orphans.iterdir():
            if story_dir.is_dir() and parse_key_from_dirname(story_dir.name) == key:
                return story_dir
    return None


def resolve_context(start: Optional[Path] = None) -> tuple[Optional[str], Optional[str]]:
    """Inspect cwd against the .jira tree and return inferred (epic_key, story_key).

    Returns (None, None) when cwd is outside the workspace.
    """
    cwd = (start or Path.cwd()).resolve()
    ws = workspace_dir().resolve()
    try:
        rel = cwd.relative_to(ws)
    except ValueError:
        return (None, None)
    parts = rel.parts
    if not parts:
        return (None, None)
    if parts[0] == "epics":
        epic_key = parse_key_from_dirname(parts[1]) if len(parts) >= 2 else None
        story_key = parse_key_from_dirname(parts[2]) if len(parts) >= 3 else None
        return (epic_key, story_key)
    if parts[0] == "unparented":
        story_key = parse_key_from_dirname(parts[1]) if len(parts) >= 2 else None
        return (None, story_key)
    return (None, None)
