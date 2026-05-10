from __future__ import annotations

from typing import Any, Optional

from pm_shell.jira.client import JiraClient

CANONICAL_STATUSES = ("todo", "in-progress", "done", "blocked")

# Preferred Jira display names per canonical key (matched case-insensitively).
_PREFERRED_NAMES: dict[str, tuple[str, ...]] = {
    "todo": ("to do", "todo", "backlog", "open"),
    "in-progress": ("in progress", "in development", "in dev", "doing", "wip"),
    "done": ("done", "closed", "complete", "resolved"),
    "blocked": ("blocked", "on hold", "hold", "impediment"),
}

# Jira status categories: "new" → todo, "indeterminate" → in-progress, "done" → done.
# "blocked" has no native category, so we only match it by name.
_CATEGORY_FALLBACK: dict[str, str] = {
    "todo": "new",
    "in-progress": "indeterminate",
    "done": "done",
}


def _flatten_statuses(payload: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Project statuses come back grouped by issuetype; flatten and de-duplicate by name."""
    seen: dict[str, dict[str, Any]] = {}
    for issuetype in payload:
        for status in issuetype.get("statuses", []):
            name = status.get("name", "")
            if name and name not in seen:
                seen[name] = status
    return list(seen.values())


def detect_status_map(client: JiraClient, project_key: str) -> dict[str, Optional[str]]:
    """Probe the project's workflow and infer canonical→Jira status name map.

    Strategy per canonical key:
      1. Match a status by preferred display name (case-insensitive).
      2. Otherwise, fall back to the first status in the matching statusCategory.
      3. If still nothing, leave as None.
    """
    raw = client.get_project_statuses(project_key)
    statuses = _flatten_statuses(raw)
    by_lower_name = {s["name"].lower(): s for s in statuses}

    mapping: dict[str, Optional[str]] = {}
    for canonical in CANONICAL_STATUSES:
        match: Optional[str] = None
        for preferred in _PREFERRED_NAMES[canonical]:
            if preferred in by_lower_name:
                match = by_lower_name[preferred]["name"]
                break
        if match is None and canonical in _CATEGORY_FALLBACK:
            target_category = _CATEGORY_FALLBACK[canonical]
            for status in statuses:
                category = (status.get("statusCategory") or {}).get("key")
                if category == target_category:
                    match = status["name"]
                    break
        mapping[canonical] = match
    return mapping
