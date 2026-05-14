"""Seed local workspace with N epics x M stories (+ subtasks/comments) for stress-testing merge.

Bypasses the typer CLI so we can scaffold ~200 dirty records in <1s of Python time;
the slow part is pm merge itself talking to Jira.
"""

from __future__ import annotations

import sys
import time

from pm_shell.commands._mutate import append_comment, next_local_key
from pm_shell.config import load_config
from pm_shell.render.adf import plain_to_adf
from pm_shell.workspace.io import atomic_write_json
from pm_shell.workspace.paths import epics_dir, issue_dirname


def _epic_record(cfg, key: str, summary: str) -> dict:
    return {
        "key": key,
        "issueType": "Epic",
        "summary": summary,
        "status": "todo",
        "statusJira": cfg.status_map.get("todo"),
        "priority": "medium",
        "owner": None,
        "labels": ["stress-test"],
        "description": plain_to_adf(f"Stress-test epic: {summary}"),
        "_unpushed": True,
    }


def _story_record(cfg, key: str, summary: str, epic_key: str) -> dict:
    return {
        "key": key,
        "issueType": "Story",
        "summary": summary,
        "status": "todo",
        "statusJira": cfg.status_map.get("todo"),
        "priority": "high",
        "assignee": None,
        "labels": ["stress-test"],
        "epic": epic_key,
        "points": None,
        "description": plain_to_adf(f"Stress-test story under {epic_key}"),
        "_unpushed": True,
    }


def _subtask_record(idx: int, title: str, cfg) -> dict:
    return {
        "id": idx,
        "key": None,
        "title": title,
        "done": False,
        "status": "todo",
        "statusJira": cfg.status_map.get("todo"),
        "assignee": None,
        "_unpushed": True,
    }


def main(epics: int, stories_per_epic: int, subtasks_per_story: int) -> None:
    cfg = load_config()
    epics_root = epics_dir()
    epics_root.mkdir(parents=True, exist_ok=True)

    t0 = time.perf_counter()
    epic_keys: list[str] = []
    story_count = 0
    subtask_count = 0
    comment_count = 0

    for i in range(1, epics + 1):
        ek = next_local_key(cfg)
        epic_keys.append(ek)
        summary = f"Stress epic {i}"
        record = _epic_record(cfg, ek, summary)
        edir = epics_root / issue_dirname(ek, summary)
        edir.mkdir(parents=True, exist_ok=False)
        atomic_write_json(edir / "epic.json", record)

        for j in range(1, stories_per_epic + 1):
            sk = next_local_key(cfg)
            story_count += 1
            ssummary = f"Stress story {i}.{j}"
            srecord = _story_record(cfg, sk, ssummary, ek)
            sdir = edir / issue_dirname(sk, ssummary)
            sdir.mkdir(parents=True, exist_ok=False)
            atomic_write_json(sdir / "story.json", srecord)

            tasks = [
                _subtask_record(idx + 1, f"Subtask {idx + 1} of {sk}", cfg)
                for idx in range(subtasks_per_story)
            ]
            atomic_write_json(sdir / "tasks.json", tasks)
            atomic_write_json(sdir / "comments.json", [])
            subtask_count += len(tasks)

            append_comment(sk, f"Initial comment on stress story {sk}", cfg=cfg)
            comment_count += 1

    dt = time.perf_counter() - t0
    print(
        f"seeded {len(epic_keys)} epics, {story_count} stories, "
        f"{subtask_count} subtasks, {comment_count} comments in {dt:.2f}s"
    )
    print(f"epic keys: {epic_keys[0]} .. {epic_keys[-1]}")


if __name__ == "__main__":
    n_epics = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    n_stories = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    n_subtasks = int(sys.argv[3]) if len(sys.argv) > 3 else 2
    main(n_epics, n_stories, n_subtasks)
