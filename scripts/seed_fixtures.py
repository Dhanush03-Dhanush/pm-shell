"""Seed the configured Jira project with a small fixture set for testing.

Creates 3 epics, 5 stories, 5 sub-tasks, and 1 comment via the Jira REST API.
Idempotency is NOT guaranteed — re-running creates duplicates. Delete via the
Jira UI to start fresh.

Run via: uv run python scripts/seed_fixtures.py
"""

from __future__ import annotations

from typing import Any, Optional

from pm_shell.config import load_config
from pm_shell.jira.client import JiraClient


def _adf(text: str) -> dict[str, Any]:
    """Wrap a plain string into a minimal Atlassian Document Format payload."""
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": text}]}
        ],
    }


def _pick_issue_type(issue_types: list[dict[str, Any]], *, want_epic: bool = False, want_subtask: bool = False) -> str:
    """Choose an issue type name from the project's available types."""
    if want_epic:
        for it in issue_types:
            if it.get("name", "").lower() == "epic":
                return it["name"]
        for it in issue_types:
            if it.get("hierarchyLevel") == 1:
                return it["name"]
        raise RuntimeError("No Epic issue type found in project.")

    if want_subtask:
        for preferred in ("sub-task", "subtask"):
            for it in issue_types:
                if it.get("name", "").lower() == preferred:
                    return it["name"]
        for it in issue_types:
            if it.get("subtask"):
                return it["name"]
        raise RuntimeError("No Sub-task issue type found in project.")

    for preferred in ("story", "task"):
        for it in issue_types:
            if it.get("name", "").lower() == preferred and not it.get("subtask"):
                return it["name"]
    for it in issue_types:
        if not it.get("subtask") and it.get("name", "").lower() != "epic":
            return it["name"]
    raise RuntimeError("No Story-like issue type found in project.")


def create_issue(
    client: JiraClient,
    project_key: str,
    issuetype_name: str,
    summary: str,
    *,
    parent_key: Optional[str] = None,
    priority: Optional[str] = None,
    description: Optional[str] = None,
    labels: Optional[list[str]] = None,
) -> str:
    fields: dict[str, Any] = {
        "project": {"key": project_key},
        "issuetype": {"name": issuetype_name},
        "summary": summary,
    }
    if parent_key:
        fields["parent"] = {"key": parent_key}
    if priority:
        fields["priority"] = {"name": priority}
    if description:
        fields["description"] = _adf(description)
    if labels:
        fields["labels"] = labels

    result = client.post("/rest/api/3/issue", json={"fields": fields})
    return result["key"]


def add_comment(client: JiraClient, issue_key: str, body: str) -> None:
    client.post(f"/rest/api/3/issue/{issue_key}/comment", json={"body": _adf(body)})


def main() -> None:
    cfg = load_config()
    with JiraClient(cfg) as client:
        if cfg.board_id is None:
            raise SystemExit("config.json has no boardId")
        board = client.get_board(cfg.board_id)
        project_key = board["location"]["projectKey"]
        print(f"Project: {project_key}")

        project = client.get(f"/rest/api/3/project/{project_key}")
        issue_types = project.get("issueTypes", [])
        print(f"Issue types: {[t['name'] for t in issue_types]}")

        epic_type = _pick_issue_type(issue_types, want_epic=True)
        story_type = _pick_issue_type(issue_types)
        subtask_type = _pick_issue_type(issue_types, want_subtask=True)
        print(f"Using: epic={epic_type}, story={story_type}, sub-task={subtask_type}")

        # Epic 1: Auth overhaul
        e1 = create_issue(client, project_key, epic_type, "Auth overhaul",
                          description="Replace legacy session auth with OIDC-backed SSO.",
                          labels=["auth", "security"])
        print(f"  epic {e1}: Auth overhaul")

        s1a = create_issue(client, project_key, story_type, "SSO integration",
                           parent_key=e1, priority="High",
                           description="Wire Okta SAML against the new auth gateway.",
                           labels=["sso"])
        print(f"    story {s1a}: SSO integration")
        for st in ("Wire OAuth callback", "Add session persistence", "Token refresh job"):
            t = create_issue(client, project_key, subtask_type, st, parent_key=s1a)
            print(f"      sub-task {t}: {st}")

        s1b = create_issue(client, project_key, story_type, "Session refresh",
                           parent_key=e1, priority="Medium")
        print(f"    story {s1b}: Session refresh")

        add_comment(client, s1a, "Blocking on Okta tenant provisioning — ETA Friday.")
        print(f"      + comment on {s1a}")

        # Epic 2: Onboarding flow
        e2 = create_issue(client, project_key, epic_type, "Onboarding flow",
                          description="Net-new user onboarding from signup to first action.",
                          labels=["onboarding"])
        print(f"  epic {e2}: Onboarding flow")

        s2a = create_issue(client, project_key, story_type, "Welcome screen",
                           parent_key=e2, priority="Medium")
        print(f"    story {s2a}: Welcome screen")
        for st in ("Copy review", "Animation polish"):
            t = create_issue(client, project_key, subtask_type, st, parent_key=s2a)
            print(f"      sub-task {t}: {st}")

        s2b = create_issue(client, project_key, story_type, "Email verification",
                           parent_key=e2, priority="Low")
        print(f"    story {s2b}: Email verification")

        # Epic 3: Performance pass
        e3 = create_issue(client, project_key, epic_type, "Performance pass",
                          description="Identify and fix the top P99 hotspots in the request path.",
                          labels=["perf"])
        print(f"  epic {e3}: Performance pass")

        s3a = create_issue(client, project_key, story_type, "Query profiling",
                           parent_key=e3, priority="High")
        print(f"    story {s3a}: Query profiling")

    print("Done.")


if __name__ == "__main__":
    main()
