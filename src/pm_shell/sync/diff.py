"""Detect and render local changes vs. the cloned baseline.

The "baseline" is the raw Jira payload stored in `.jira/.baseline/<KEY>.json`
when we last pulled. To compare it against the current workspace shape,
re-apply the same converters `clone` used (`sync/shape.py`) and diff.

Outputs:
    - `compute_changes()` returns a flat `list[Change]` of every file-level
      delta (epic.json, story.json, tasks.json, comments.json — one per file).
    - `format_diff_text(before, after)` renders a unified diff into a
      rich Text with +/− coloring, suitable for printing or for stuffing
      into a Textual widget.

Granularity is per-file rather than per-field: `git diff` familiarity for
end users, simple data flow for us. Push (Phase 6) will need finer-grained
inspection of changed fields but can do that lazily when applying each item.
"""

from __future__ import annotations

import difflib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from rich.text import Text

from pm_shell.config import load_config
from pm_shell.sync.shape import epic_shape, story_shape, task_shape
from pm_shell.workspace.io import read_json
from pm_shell.workspace.paths import (
    baseline_dir,
    epics_dir,
    parse_key_from_dirname,
    unparented_dir,
)

# ── Data model ──────────────────────────────────────────────────────────────

ChangeKind = str  # "created" | "modified" | "deleted"
IssueType = str   # "epic" | "story" | "tasks" | "comments"


@dataclass
class Change:
    """One file-level delta between workspace and baseline."""

    file_label: str  # e.g. "KAN-5/story.json" — shown in the file list
    key: str         # the issue key this change belongs to (KAN-5, NEW-1, ...)
    kind: ChangeKind
    issue_type: IssueType
    summary: str = ""
    before_json: Optional[str] = None
    after_json: Optional[str] = None
    notes: list[str] = field(default_factory=list)  # human-readable, e.g. "+2 tasks, -1 comment"


# ── Baseline loading ────────────────────────────────────────────────────────


def _load_baseline_raw(key: str) -> Optional[dict[str, Any]]:
    path = baseline_dir() / f"{key}.json"
    if not path.exists():
        return None
    return read_json(path)


def _status_map() -> dict[str, Optional[str]]:
    try:
        return dict(load_config().status_map)
    except Exception:
        return {}


def _baseline_epic(key: str) -> Optional[dict[str, Any]]:
    raw = _load_baseline_raw(key)
    return epic_shape(raw, _status_map()) if raw else None


def _baseline_story(key: str, epic_key: Optional[str]) -> Optional[dict[str, Any]]:
    raw = _load_baseline_raw(key)
    return story_shape(raw, _status_map(), epic_key) if raw else None


def _baseline_tasks_for_story(story_key: str) -> list[dict[str, Any]]:
    """Reconstruct the cloned tasks list by walking sub-task baselines whose parent is story_key."""
    sm = _status_map()
    subtask_baselines: list[dict[str, Any]] = []
    for path in sorted(baseline_dir().glob("*.json")):
        raw = read_json(path)
        fields = raw.get("fields") or {}
        parent_key = (fields.get("parent") or {}).get("key")
        issuetype = fields.get("issuetype") or {}
        if parent_key == story_key and issuetype.get("subtask"):
            subtask_baselines.append(raw)
    return [task_shape(i + 1, st, sm) for i, st in enumerate(subtask_baselines)]


# ── JSON helpers ────────────────────────────────────────────────────────────


def _pretty_json(data: Any) -> str:
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


# ── Change detection ────────────────────────────────────────────────────────


def _epic_change(epic_dir: Path) -> Optional[Change]:
    path = epic_dir / "epic.json"
    if not path.exists():
        return None
    current = read_json(path)
    key = current["key"]
    summary = current.get("summary", "")
    label = f"{key}/epic.json"

    if current.get("_unpushed"):
        return Change(label, key, "created", "epic", summary, None, _pretty_json(current))

    baseline = _baseline_epic(key)
    if current.get("_deleted"):
        return Change(label, key, "deleted", "epic", summary,
                      _pretty_json(baseline) if baseline else None,
                      _pretty_json(current))

    if baseline is None:
        return None
    if current != baseline:
        return Change(label, key, "modified", "epic", summary,
                      _pretty_json(baseline), _pretty_json(current))
    return None


def _story_changes(story_dir: Path, parent_epic_key: Optional[str]) -> list[Change]:
    out: list[Change] = []
    story_path = story_dir / "story.json"
    if not story_path.exists():
        return out
    current = read_json(story_path)
    key = current["key"]
    summary = current.get("summary", "")

    # story.json
    story_label = f"{key}/story.json"
    if current.get("_unpushed"):
        out.append(Change(story_label, key, "created", "story", summary, None, _pretty_json(current)))
    elif current.get("_deleted"):
        baseline = _baseline_story(key, parent_epic_key)
        out.append(Change(story_label, key, "deleted", "story", summary,
                          _pretty_json(baseline) if baseline else None,
                          _pretty_json(current)))
    else:
        baseline = _baseline_story(key, parent_epic_key)
        if baseline is not None and current != baseline:
            out.append(Change(story_label, key, "modified", "story", summary,
                              _pretty_json(baseline), _pretty_json(current)))

    # tasks.json
    tasks_path = story_dir / "tasks.json"
    if tasks_path.exists():
        current_tasks = read_json(tasks_path)
        baseline_tasks = _baseline_tasks_for_story(key)
        if current_tasks != baseline_tasks:
            kind = "created" if not baseline_tasks else "modified"
            out.append(Change(
                f"{key}/tasks.json", key, kind, "tasks", summary,
                _pretty_json(baseline_tasks),
                _pretty_json(current_tasks),
                notes=_task_notes(baseline_tasks, current_tasks),
            ))

    # comments.json — only surface newly added (_unpushed) comments
    comments_path = story_dir / "comments.json"
    if comments_path.exists():
        current_comments = read_json(comments_path)
        new_comments = [c for c in current_comments if c.get("_unpushed")]
        if new_comments:
            out.append(Change(
                f"{key}/comments.json", key, "created", "comments", summary,
                _pretty_json([c for c in current_comments if not c.get("_unpushed")]),
                _pretty_json(current_comments),
                notes=[f"+{len(new_comments)} unpushed comment(s)"],
            ))
    return out


def _task_notes(before: list[dict], after: list[dict]) -> list[str]:
    before_keys = {t.get("key") for t in before if t.get("key")}
    after_keys = {t.get("key") for t in after if t.get("key")}
    new_count = sum(1 for t in after if t.get("_unpushed"))
    removed = before_keys - after_keys
    modified = sum(
        1 for t in after
        if t.get("key") and t.get("key") in before_keys
        and t not in before
    )
    notes = []
    if new_count:
        notes.append(f"+{new_count} new")
    if removed:
        notes.append(f"-{len(removed)} deleted")
    if modified:
        notes.append(f"~{modified} modified")
    return notes


def compute_changes() -> list[Change]:
    """Walk the workspace and return every file-level change vs. baseline."""
    changes: list[Change] = []

    # Epics + their child stories
    if epics_dir().exists():
        for ed in sorted(epics_dir().iterdir()):
            if not ed.is_dir():
                continue
            ec = _epic_change(ed)
            if ec is not None:
                changes.append(ec)
            epic_key = parse_key_from_dirname(ed.name)
            for sd in sorted(ed.iterdir()):
                if sd.is_dir():
                    changes.extend(_story_changes(sd, epic_key))

    # Unparented stories
    orphans = unparented_dir()
    if orphans.exists():
        for sd in sorted(orphans.iterdir()):
            if sd.is_dir():
                changes.extend(_story_changes(sd, None))

    return changes


# ── Diff rendering ──────────────────────────────────────────────────────────

# Background tints applied to + / - lines so the diff reads like git's
# `--color=always` output (green/red highlights). Dark RGBs keep the bright
# foreground text legible on most terminal themes.
_ADD_STYLE = "green on #103820"
_DEL_STYLE = "red on #401818"
_HEADER_STYLE = "bold"
_HUNK_STYLE = "cyan bold"
_CONTEXT_STYLE = "white dim"

# Pad each line to this many columns so the background fills the visible row.
# Terminals will clip beyond their actual width; lines shorter than this get
# the highlight all the way to the right edge.
_LINE_PAD_WIDTH = 240


def format_diff_text(
    before_json: Optional[str],
    after_json: Optional[str],
    *,
    before_label: str = "baseline",
    after_label: str = "current",
) -> Text:
    """Render a unified diff as a rich Text. Empty Text when both sides are identical."""
    before_lines = (before_json or "").splitlines(keepends=False)
    after_lines = (after_json or "").splitlines(keepends=False)

    diff = list(difflib.unified_diff(
        before_lines, after_lines,
        fromfile=before_label, tofile=after_label,
        lineterm="",
    ))
    if not diff:
        return Text("(no textual diff — files identical)", style="dim")

    result = Text()
    for line in diff:
        style, padded = _style_and_pad(line)
        result.append(padded + "\n", style=style)
    return result


def _style_and_pad(line: str) -> tuple[str, str]:
    """Pick the style and pad the line so its background extends across the row.

    Headers and hunk markers aren't padded — they're short and the styling is
    foreground-only, so trailing spaces would just be wasted ink.
    """
    if line.startswith("+++") or line.startswith("---"):
        return _HEADER_STYLE, line
    if line.startswith("@@"):
        return _HUNK_STYLE, line
    if line.startswith("+"):
        return _ADD_STYLE, line.ljust(_LINE_PAD_WIDTH)
    if line.startswith("-"):
        return _DEL_STYLE, line.ljust(_LINE_PAD_WIDTH)
    return _CONTEXT_STYLE, line
