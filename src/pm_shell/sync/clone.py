from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from pm_shell.config import Config, save_config, workspace_dir
from pm_shell.jira.client import DEFAULT_ISSUE_FIELDS, JiraClient
from pm_shell.sync.shape import comment_shape, epic_shape, story_shape, task_shape
from pm_shell.sync.workflow import detect_status_map
from pm_shell.workspace.io import atomic_write_json
from pm_shell.workspace.paths import (
    baseline_dir,
    epics_dir,
    issue_dirname,
    unparented_dir,
)


class DirtyWorkspaceError(RuntimeError):
    """Refused to clone because .jira/epics/ already has content."""


ProgressFn = Callable[[str], None]


def _noop(_: str) -> None:
    pass


def _parent_key(issue: dict[str, Any]) -> Optional[str]:
    parent = issue.get("fields", {}).get("parent")
    if not parent:
        return None
    return parent.get("key")


def clone(
    config: Config,
    *,
    force: bool = False,
    progress: ProgressFn = _noop,
) -> dict[str, int]:
    """Clone the configured Jira board into .jira/. Returns summary counts."""
    if config.board_id is None:
        raise RuntimeError("No boardId set in config. Add it to .jira/config.json.")

    epics_root = epics_dir()
    if epics_root.exists() and any(epics_root.iterdir()) and not force:
        raise DirtyWorkspaceError(
            f"{epics_root} already exists and is non-empty. Re-run with --force to overwrite."
        )

    with JiraClient(config) as client:
        progress(f"Resolving board {config.board_id}…")
        board = client.get_board(config.board_id)
        location = board.get("location") or {}
        project_key = location.get("projectKey")
        if not project_key:
            raise RuntimeError(f"Could not determine project key for board {config.board_id}.")
        progress(f"Project: {project_key} ({location.get('projectName', '')})")

        progress("Detecting status workflow…")
        status_map = detect_status_map(client, project_key)
        progress(f"Status map: {status_map}")

        progress("Fetching all issues…")
        all_issues = list(
            client.search_jql(
                f"project = {project_key} ORDER BY key ASC",
                fields=DEFAULT_ISSUE_FIELDS,
            )
        )
        progress(f"Fetched {len(all_issues)} issue(s)")

    epics: list[dict[str, Any]] = []
    stories: list[dict[str, Any]] = []
    subtasks: list[dict[str, Any]] = []
    for issue in all_issues:
        itype = (issue.get("fields", {}).get("issuetype") or {})
        if itype.get("subtask"):
            subtasks.append(issue)
        elif itype.get("name", "").lower() == "epic":
            epics.append(issue)
        else:
            stories.append(issue)

    subtasks_by_parent: dict[str, list[dict[str, Any]]] = {}
    for st in subtasks:
        pk = _parent_key(st)
        if pk:
            subtasks_by_parent.setdefault(pk, []).append(st)

    _wipe_tree_for_clone(force=force)
    epics_root.mkdir(parents=True, exist_ok=True)
    baseline_root = baseline_dir()
    baseline_root.mkdir(parents=True, exist_ok=True)

    epic_dirs: dict[str, Path] = {}
    for epic in epics:
        record = epic_shape(epic, status_map)
        dirname = issue_dirname(record["key"], record["summary"])
        edir = epics_root / dirname
        edir.mkdir(parents=True, exist_ok=True)
        atomic_write_json(edir / "epic.json", record)
        atomic_write_json(baseline_root / f"{record['key']}.json", epic)
        epic_dirs[record["key"]] = edir
        progress(f"  epic {record['key']}: {record['summary']}")

    unparented_root: Optional[Path] = None
    comment_count = 0
    task_count = 0
    with JiraClient(config) as client:
        for story in stories:
            parent = _parent_key(story)
            epic_dir = epic_dirs.get(parent) if parent else None
            if epic_dir is None:
                if unparented_root is None:
                    unparented_root = unparented_dir()
                    unparented_root.mkdir(parents=True, exist_ok=True)
                container = unparented_root
                effective_epic_key = None
            else:
                container = epic_dir
                effective_epic_key = parent

            srecord = story_shape(story, status_map, effective_epic_key)
            sdirname = issue_dirname(srecord["key"], srecord["summary"])
            sdir = container / sdirname
            sdir.mkdir(parents=True, exist_ok=True)
            atomic_write_json(sdir / "story.json", srecord)
            atomic_write_json(baseline_root / f"{srecord['key']}.json", story)

            story_subs = subtasks_by_parent.get(srecord["key"], [])
            tasks = [
                task_shape(i + 1, st, status_map) for i, st in enumerate(story_subs)
            ]
            atomic_write_json(sdir / "tasks.json", tasks)
            for st in story_subs:
                atomic_write_json(baseline_root / f"{st['key']}.json", st)
            task_count += len(tasks)

            progress(f"    story {srecord['key']}: {srecord['summary']} ({len(tasks)} task(s))")

            comments = client.get_comments(srecord["key"])
            atomic_write_json(
                sdir / "comments.json",
                [comment_shape(c) for c in comments],
            )
            comment_count += len(comments)

    config.status_map = {k: v for k, v in status_map.items() if v}
    config.last_pull_at = datetime.now(timezone.utc).isoformat()
    config.project_key = project_key
    save_config(config)

    return {
        "epics": len(epics),
        "stories": len(stories),
        "tasks": task_count,
        "comments": comment_count,
    }


def _wipe_tree_for_clone(*, force: bool) -> None:
    """When force-re-cloning, remove the on-disk tree (epics/, unparented/, .baseline/).
    config.json is preserved.
    """
    if not force:
        return
    import shutil

    root = workspace_dir()
    for sub in ("epics", "unparented", ".baseline"):
        target = root / sub
        if target.exists():
            shutil.rmtree(target)
