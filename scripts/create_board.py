"""Create a new Jira project that mirrors KAN's config.

Reads a JSON spec (default: scripts/board_config.json), authenticates with the
.jira/config.json in the current workspace, and POSTs /rest/api/3/project. On
success, prints the new project + board IDs and the snippet you can drop into a
fresh `jira-secrets.json` for `pm config init` + `pm clone`.

Usage:
    cp scripts/board_config.example.json scripts/board_config.json
    # edit key/name in the json
    .venv/bin/python scripts/create_board.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from pm_shell.config import load_config, save_config
from pm_shell.jira.client import JiraClient, JiraHTTPError

DEFAULT_SPEC = Path(__file__).resolve().parent / "board_config.json"
KEY_RE = re.compile(r"^[A-Z][A-Z0-9]{1,9}$")


class SpecError(ValueError):
    pass


def _strip_comments(raw: dict) -> dict:
    """Drop keys that start with `//` so the JSON can carry inline notes."""
    return {k: v for k, v in raw.items() if not k.startswith("//")}


def _validate(spec: dict) -> None:
    for required in ("key", "name", "projectTypeKey", "projectTemplateKey"):
        if not spec.get(required):
            raise SpecError(f"spec is missing required field: {required!r}")
    if not KEY_RE.match(spec["key"]):
        raise SpecError(
            f"invalid project key {spec['key']!r}: must be 2–10 uppercase letters/digits, starting with a letter"
        )


def _create_project(client: JiraClient, spec: dict) -> dict:
    body = {
        "key": spec["key"],
        "name": spec["name"],
        "projectTypeKey": spec["projectTypeKey"],
        "projectTemplateKey": spec["projectTemplateKey"],
        "leadAccountId": spec["leadAccountId"],
        "assigneeType": spec.get("assigneeType", "UNASSIGNED"),
    }
    if spec.get("description"):
        body["description"] = spec["description"]
    return client.post("/rest/api/3/project", json=body)


def _find_board(client: JiraClient, project_key: str) -> int | None:
    """Team-managed templates auto-create a board; locate it by project key."""
    page = client.get("/rest/agile/1.0/board", params={"projectKeyOrId": project_key})
    values = page.get("values") or []
    return values[0]["id"] if values else None


def _print_next_steps(project_key: str, board_id: int | None, config_updated: bool) -> None:
    print()
    if config_updated:
        print("Workspace .jira/config.json now points at the new project.")
        print("Next:")
        print("  pm clone        # mirror the (empty) new board into .jira/")
        print("  pm              # open the interactive shell")
    else:
        print(f"Set boardId={board_id} (project {project_key}) in your workspace's")
        print(".jira/config.json, then run `pm clone`.")


def main(spec_path: Path) -> int:
    if not spec_path.exists():
        print(
            f"error: spec file not found: {spec_path}\n"
            f"hint:  cp {spec_path.parent / 'board_config.example.json'} {spec_path}",
            file=sys.stderr,
        )
        return 2

    spec = _strip_comments(json.loads(spec_path.read_text()))
    try:
        _validate(spec)
    except SpecError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    cfg = load_config()
    with JiraClient(cfg) as client:
        if not spec.get("leadAccountId"):
            spec["leadAccountId"] = client.myself()["accountId"]
            print(f"using authenticated user as project lead: {spec['leadAccountId']}")

        try:
            project = _create_project(client, spec)
        except JiraHTTPError as exc:
            print(f"create-project failed: {exc.status_code} {exc.body}", file=sys.stderr)
            return 1

        board_id = _find_board(client, project["key"])

    config_updated = False
    if board_id is not None:
        cfg.board_id = board_id
        cfg.project_key = project["key"]
        cfg.last_pull_at = None
        save_config(cfg)
        config_updated = True

    print()
    print(f"  project key : {project['key']}")
    print(f"  project id  : {project['id']}")
    print(f"  board id    : {board_id if board_id is not None else '(not auto-created — create one in Jira UI)'}")
    _print_next_steps(project["key"], board_id, config_updated)
    return 0


if __name__ == "__main__":
    arg = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SPEC
    sys.exit(main(arg))
