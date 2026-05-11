"""Raw Jira payload → workspace shape converters.

Used by both `clone` (writing fresh epic.json / story.json / tasks.json / comments.json)
and `diff` (re-deriving the baseline shape from the stored raw payload at compare-time).
Keeping the conversion in one place ensures clone and diff agree on what fields end up
in the workspace.
"""

from __future__ import annotations

from typing import Any, Optional

StatusMap = dict[str, Optional[str]]


def user_record(user: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if not user:
        return None
    return {
        "accountId": user.get("accountId"),
        "displayName": user.get("displayName"),
        "email": user.get("emailAddress"),
    }


def canonicalize_status(status_name: str, status_map: StatusMap) -> Optional[str]:
    """Map a Jira status name (e.g. 'In Progress') to canonical (todo|in-progress|done|blocked)."""
    if not status_name:
        return None
    target = status_name.lower()
    for canonical, jira_name in status_map.items():
        if jira_name and jira_name.lower() == target:
            return canonical
    return None


def epic_shape(issue: dict[str, Any], status_map: StatusMap) -> dict[str, Any]:
    fields = issue.get("fields", {})
    status = fields.get("status") or {}
    status_name = status.get("name", "")
    return {
        "key": issue["key"],
        "issueType": (fields.get("issuetype") or {}).get("name"),
        "summary": fields.get("summary", ""),
        "status": canonicalize_status(status_name, status_map),
        "statusJira": status_name,
        "priority": (fields.get("priority") or {}).get("name", "").lower() or None,
        "owner": user_record(fields.get("assignee")),
        "labels": fields.get("labels") or [],
        "description": fields.get("description"),
        "created": fields.get("created"),
        "updated": fields.get("updated"),
    }


def story_shape(
    issue: dict[str, Any],
    status_map: StatusMap,
    epic_key: Optional[str],
) -> dict[str, Any]:
    fields = issue.get("fields", {})
    status = fields.get("status") or {}
    status_name = status.get("name", "")
    return {
        "key": issue["key"],
        "issueType": (fields.get("issuetype") or {}).get("name"),
        "summary": fields.get("summary", ""),
        "status": canonicalize_status(status_name, status_map),
        "statusJira": status_name,
        "priority": (fields.get("priority") or {}).get("name", "").lower() or None,
        "assignee": user_record(fields.get("assignee")),
        "labels": fields.get("labels") or [],
        "epic": epic_key,
        "description": fields.get("description"),
        "created": fields.get("created"),
        "updated": fields.get("updated"),
    }


def task_shape(index: int, issue: dict[str, Any], status_map: StatusMap) -> dict[str, Any]:
    fields = issue.get("fields", {})
    status = fields.get("status") or {}
    status_name = status.get("name", "")
    canonical = canonicalize_status(status_name, status_map)
    return {
        "id": index,
        "key": issue["key"],
        "title": fields.get("summary", ""),
        "done": canonical == "done",
        "status": canonical,
        "statusJira": status_name,
        "assignee": user_record(fields.get("assignee")),
    }


def comment_shape(comment: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": comment.get("id"),
        "author": user_record(comment.get("author")),
        "body": comment.get("body"),
        "created": comment.get("created"),
        "updated": comment.get("updated"),
    }
