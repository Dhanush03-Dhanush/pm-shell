"""Push local workspace changes to Jira (Phase 6).

Walks `.jira/` for items marked `_unpushed`, `_deleted`, or modified vs. baseline,
and replays them via the Jira REST API. After each successful operation, local
state is updated so the workspace matches Jira (real keys replace NEW-* placeholders,
baselines refresh, `_unpushed`/`_deleted` markers are removed).

Operation order matters and reflects real-world dependencies:

    1. Create new epics                 (so child stories can reference real keys)
    2. Create new stories               (parent epic key, possibly just created, resolved)
    3. Create new sub-tasks             (parent story key, possibly just created, resolved)
    4. Update existing epics/stories    (fields via PUT, status via /transitions)
    5. Post new comments
    6. Delete stories (then epics)      (Jira refuses to delete an epic with child issues)

Limitations (v1):
    - No conflict detection: we don't re-fetch and compare baselines before
      writing. Last-write-wins. For solo workspaces this is fine; collaborative
      use needs a later phase.
    - Sub-task modifications and deletions are not handled. Tasks are
      append-and-flip-done in practice; full edit support is a follow-up.
    - Assignee/owner: we resolve email → accountId via /user/search. If no
      match, the field is sent as null and a warning lands in the outcome.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from pm_shell.config import Config, save_config
from pm_shell.jira.client import JiraClient, JiraHTTPError
from pm_shell.sync.shape import (
    comment_shape,
    epic_shape,
    story_shape,
    task_shape,
)
from pm_shell.workspace.io import atomic_write_json, read_json
from pm_shell.workspace.paths import (
    baseline_dir,
    epics_dir,
    issue_dirname,
    log_dir,
    parse_key_from_dirname,
    unparented_dir,
)


class PushError(RuntimeError):
    """Halts the merge entirely (config missing, etc.) — not per-item."""


ProgressFn = Callable[[str], None]


def _noop(_: str) -> None:
    pass


# ── Outcome record ──────────────────────────────────────────────────────────


@dataclass
class PushOutcome:
    """What merge() did. Suitable for printing and for the .jira/.log entry."""

    successes: list[str] = field(default_factory=list)
    failures: list[tuple[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    started_at: str = field(default_factory=lambda: _now())
    finished_at: Optional[str] = None
    dry_run: bool = False

    def ok(self, msg: str) -> None:
        self.successes.append(msg)

    def fail(self, label: str, reason: str) -> None:
        self.failures.append((label, reason))

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    @property
    def total(self) -> int:
        return len(self.successes) + len(self.failures)


# ── Per-merge context ───────────────────────────────────────────────────────


@dataclass
class _Context:
    """Mutable state threaded through every push operation."""

    client: JiraClient
    project_key: str
    status_map: dict[str, Optional[str]]
    accountid_cache: dict[str, Optional[str]] = field(default_factory=dict)
    # NEW-1 → KAN-99 once the parent has landed; used to rewrite story.epic refs.
    new_key_map: dict[str, str] = field(default_factory=dict)
    # Local keys whose parent issue was created (or, in dry-run, would have been
    # created) earlier in this merge. Lets child phases preview their work even
    # though the on-disk `_unpushed` flag is still set in dry-run mode.
    created_keys: set[str] = field(default_factory=set)
    # Story Points field ID for this tenant. Different Jira projects assign different
    # custom-field IDs (commonly customfield_10016 in classic scrum, 10026 in team-managed,
    # absent entirely in basic kanban). Resolved lazily and cached for the merge.
    points_field_id: Optional[str] = None
    points_field_resolved: bool = False
    # canonical priority (low/medium/high/critical) → Jira priority display name
    # ("Low"/"High"/"Highest"/...). Resolved lazily from /rest/api/3/priority since
    # tenants vary (some use Highest..Lowest, some use Critical..Trivial, some custom).
    priority_map: dict[str, str] = field(default_factory=dict)
    priority_map_resolved: bool = False


# ── Public entry point ──────────────────────────────────────────────────────


def merge(
    config: Config,
    *,
    dry_run: bool = False,
    progress: ProgressFn = _noop,
) -> PushOutcome:
    """Apply every dirty item in the workspace to Jira.

    `dry_run=True` reports what *would* happen without making any API calls or
    touching local state.
    """
    project_key = config.project_key
    outcome = PushOutcome(dry_run=dry_run)
    status_map = {k: v for k, v in config.status_map.items() if v}

    with JiraClient(config) as client:
        if not project_key:
            project_key = _resolve_project_key(client, config)
            config.project_key = project_key
            save_config(config)
            progress(f"resolved projectKey={project_key} (saved to config)")
        ctx = _Context(client=client, project_key=project_key, status_map=status_map)

        _phase_create_epics(ctx, outcome, dry_run, progress)
        _phase_create_stories(ctx, outcome, dry_run, progress)
        _phase_create_subtasks(ctx, outcome, dry_run, progress)
        _phase_update_issues(ctx, outcome, dry_run, progress)
        _phase_create_comments(ctx, outcome, dry_run, progress)
        _phase_delete_stories(ctx, outcome, dry_run, progress)
        _phase_delete_epics(ctx, outcome, dry_run, progress)

    outcome.finished_at = _now()
    if not dry_run:
        _write_log(outcome, config)
    return outcome


# ── Phases ──────────────────────────────────────────────────────────────────


def _phase_create_epics(ctx: _Context, outcome: PushOutcome, dry_run: bool, progress: ProgressFn) -> None:
    for edir, record in _iter_epics():
        if record.get("_unpushed") and not record.get("_deleted"):
            _push_create_epic(ctx, edir, record, outcome, dry_run, progress)


def _phase_create_stories(ctx: _Context, outcome: PushOutcome, dry_run: bool, progress: ProgressFn) -> None:
    for sdir, record, epic_dir in _iter_stories():
        if record.get("_unpushed") and not record.get("_deleted"):
            _push_create_story(ctx, sdir, record, epic_dir, outcome, dry_run, progress)


def _phase_create_subtasks(ctx: _Context, outcome: PushOutcome, dry_run: bool, progress: ProgressFn) -> None:
    for sdir, story, _ in _iter_stories(skip_deleted=True):
        # Skip subtasks whose parent story never made it to Jira (or whose creation
        # failed this run). `created_keys` covers the dry-run case where the parent
        # was previewed but `_unpushed` is still on disk.
        if story.get("_unpushed") and story["key"] not in ctx.created_keys:
            continue
        tasks_path = sdir / "tasks.json"
        if not tasks_path.exists():
            continue
        tasks = read_json(tasks_path)
        for idx, task in enumerate(tasks):
            if not task.get("_unpushed") or task.get("key"):
                continue
            _push_create_subtask(ctx, sdir, story, tasks, idx, outcome, dry_run, progress)


def _phase_update_issues(ctx: _Context, outcome: PushOutcome, dry_run: bool, progress: ProgressFn) -> None:
    for edir, record in _iter_epics():
        if record.get("_unpushed") or record.get("_deleted"):
            continue
        if _needs_update(record, _baseline_record(record["key"], "epic", ctx)):
            _push_update_issue(ctx, edir, record, "epic", outcome, dry_run, progress)

    for sdir, record, epic_dir in _iter_stories():
        if record.get("_unpushed") or record.get("_deleted"):
            continue
        epic_key_for_baseline = parse_key_from_dirname(epic_dir.name) if epic_dir is not None else None
        baseline = _baseline_record(record["key"], "story", ctx, epic_key=epic_key_for_baseline)
        if _needs_update(record, baseline):
            _push_update_issue(ctx, sdir, record, "story", outcome, dry_run, progress)


def _phase_create_comments(ctx: _Context, outcome: PushOutcome, dry_run: bool, progress: ProgressFn) -> None:
    for sdir, story, _ in _iter_stories(skip_deleted=True):
        # Same logic as the subtask phase: skip only when the parent story isn't in
        # Jira yet (i.e., its creation didn't happen / wasn't planned this run).
        if story.get("_unpushed") and story["key"] not in ctx.created_keys:
            continue
        path = sdir / "comments.json"
        if not path.exists():
            continue
        comments = read_json(path)
        for idx, comment in enumerate(comments):
            if comment.get("_unpushed"):
                story_key = ctx.new_key_map.get(story["key"], story["key"])
                _push_create_comment(ctx, story_key, comments, idx, path, outcome, dry_run, progress)


def _phase_delete_stories(ctx: _Context, outcome: PushOutcome, dry_run: bool, progress: ProgressFn) -> None:
    for sdir, record, _ in _iter_stories():
        if record.get("_deleted") and not record.get("_unpushed"):
            _push_delete_issue(ctx, sdir, record, "story", outcome, dry_run, progress)


def _phase_delete_epics(ctx: _Context, outcome: PushOutcome, dry_run: bool, progress: ProgressFn) -> None:
    for edir, record in _iter_epics(include_deleted=True):
        if record.get("_deleted") and not record.get("_unpushed"):
            _push_delete_issue(ctx, edir, record, "epic", outcome, dry_run, progress)


# ── Operations ──────────────────────────────────────────────────────────────


def _push_create_epic(
    ctx: _Context, edir: Path, record: dict, outcome: PushOutcome, dry_run: bool, progress: ProgressFn,
) -> None:
    old_key = record["key"]
    label = f"create epic {old_key} ({record.get('summary', '')!r})"
    if dry_run:
        ctx.created_keys.add(old_key)
        outcome.ok(f"would {label}")
        return

    payload = _build_create_fields(record, ctx, issue_type="Epic", parent=None, outcome=outcome)
    try:
        result = ctx.client.post("/rest/api/3/issue", json={"fields": payload})
    except JiraHTTPError as exc:
        outcome.fail(label, _format_http_error(exc))
        return

    real_key = result["key"]
    ctx.created_keys.add(old_key)
    _transition_after_create(ctx, real_key, record.get("status"), outcome)

    ctx.new_key_map[old_key] = real_key
    new_edir = _adopt_real_key(edir, "epic.json", old_key, real_key, ctx)

    for sd in new_edir.iterdir():
        if not sd.is_dir():
            continue
        spath = sd / "story.json"
        if spath.exists():
            srec = read_json(spath)
            if srec.get("epic") == old_key:
                srec["epic"] = real_key
                atomic_write_json(spath, srec)

    progress(f"epic {old_key} → {real_key}")
    outcome.ok(f"created epic {real_key} ({record.get('summary', '')!r})")


def _push_create_story(
    ctx: _Context, sdir: Path, record: dict, epic_dir: Optional[Path],
    outcome: PushOutcome, dry_run: bool, progress: ProgressFn,
) -> None:
    old_key = record["key"]
    epic_ref = ctx.new_key_map.get(record.get("epic"), record.get("epic"))

    label = f"create story {old_key} ({record.get('summary', '')!r})"
    if dry_run:
        ctx.created_keys.add(old_key)
        outcome.ok(f"would {label}")
        return

    parent_clause = {"key": epic_ref} if epic_ref else None
    payload = _build_create_fields(record, ctx, issue_type="Story", parent=parent_clause, outcome=outcome)
    try:
        result = ctx.client.post("/rest/api/3/issue", json={"fields": payload})
    except JiraHTTPError as exc:
        outcome.fail(label, _format_http_error(exc))
        return

    real_key = result["key"]
    ctx.created_keys.add(old_key)
    _transition_after_create(ctx, real_key, record.get("status"), outcome)

    ctx.new_key_map[old_key] = real_key
    _adopt_real_key(sdir, "story.json", old_key, real_key, ctx)

    progress(f"story {old_key} → {real_key}")
    outcome.ok(f"created story {real_key} ({record.get('summary', '')!r})")


def _push_create_subtask(
    ctx: _Context, sdir: Path, story: dict, tasks: list[dict], idx: int,
    outcome: PushOutcome, dry_run: bool, progress: ProgressFn,
) -> None:
    task = tasks[idx]
    label = f"create sub-task {task.get('title', '')!r} under {story['key']}"
    if dry_run:
        outcome.ok(f"would {label}")
        return

    payload: dict[str, Any] = {
        "project": {"key": ctx.project_key},
        "issuetype": {"name": "Subtask"},
        "summary": task.get("title", "").strip() or "(untitled)",
        "parent": {"key": story["key"]},
    }
    assignee = task.get("assignee")
    if isinstance(assignee, dict) and assignee.get("email"):
        account_id = _resolve_account_id(ctx, assignee["email"], outcome)
        if account_id:
            payload["assignee"] = {"accountId": account_id}

    try:
        result = ctx.client.post("/rest/api/3/issue", json={"fields": payload})
    except JiraHTTPError as exc:
        outcome.fail(label, _format_http_error(exc))
        return

    real_key = result["key"]
    _transition_after_create(ctx, real_key, task.get("status"), outcome)

    fetched = _fetch_issue(ctx.client, real_key)
    if fetched:
        atomic_write_json(baseline_dir() / f"{real_key}.json", fetched)
        new_shape = task_shape(task["id"], fetched, ctx.status_map)
        new_shape["id"] = task["id"]
        tasks[idx] = new_shape
    else:
        tasks[idx] = {**task, "key": real_key}
        tasks[idx].pop("_unpushed", None)

    atomic_write_json(sdir / "tasks.json", tasks)
    progress(f"sub-task → {real_key}")
    outcome.ok(f"created sub-task {real_key} ({task.get('title', '')!r})")


def _push_update_issue(
    ctx: _Context, item_dir: Path, record: dict, kind: str,
    outcome: PushOutcome, dry_run: bool, progress: ProgressFn,
) -> None:
    key = record["key"]
    label = f"update {kind} {key}"
    fields = _build_update_fields(record, ctx, outcome=outcome)
    canonical_status = record.get("status")

    if dry_run:
        bits = [f"PUT fields={sorted(fields)}"] if fields else []
        if canonical_status:
            bits.append(f"transition→{canonical_status}")
        outcome.ok(f"would {label}: {', '.join(bits)}")
        return

    try:
        if fields:
            ctx.client.put(f"/rest/api/3/issue/{key}", json={"fields": fields})
        if canonical_status:
            _apply_transition(ctx, key, canonical_status, outcome)
    except JiraHTTPError as exc:
        outcome.fail(label, _format_http_error(exc))
        return

    # Refresh baseline + on-disk fields after the round-trip.
    fetched = _fetch_issue(ctx.client, key)
    if fetched:
        atomic_write_json(baseline_dir() / f"{key}.json", fetched)
        if kind == "epic":
            shape = epic_shape(fetched, ctx.status_map)
        else:
            epic_key = record.get("epic")
            shape = story_shape(fetched, ctx.status_map, epic_key)
            shape["points"] = record.get("points")  # preserve user-set value
            shape["epic"] = epic_key
        record.update(shape)
        atomic_write_json(item_dir / f"{kind}.json", record)

    progress(f"{kind} {key} updated")
    outcome.ok(f"updated {kind} {key}")


def _push_create_comment(
    ctx: _Context, story_key: str, comments: list[dict], idx: int, path: Path,
    outcome: PushOutcome, dry_run: bool, progress: ProgressFn,
) -> None:
    comment = comments[idx]
    label = f"post comment on {story_key}"
    if dry_run:
        outcome.ok(f"would {label}")
        return

    try:
        result = ctx.client.post(
            f"/rest/api/3/issue/{story_key}/comment",
            json={"body": comment.get("body")},
        )
    except JiraHTTPError as exc:
        outcome.fail(label, _format_http_error(exc))
        return

    comments[idx] = comment_shape(result)
    atomic_write_json(path, comments)
    progress(f"comment on {story_key} posted")
    outcome.ok(f"posted comment on {story_key}")


def _push_delete_issue(
    ctx: _Context, item_dir: Path, record: dict, kind: str,
    outcome: PushOutcome, dry_run: bool, progress: ProgressFn,
) -> None:
    key = record["key"]
    label = f"delete {kind} {key}"
    if dry_run:
        outcome.ok(f"would {label}")
        return

    try:
        ctx.client.delete(f"/rest/api/3/issue/{key}")
    except JiraHTTPError as exc:
        outcome.fail(label, _format_http_error(exc))
        return

    # Local cleanup
    shutil.rmtree(item_dir)
    bpath = baseline_dir() / f"{key}.json"
    if bpath.exists():
        bpath.unlink()

    progress(f"{kind} {key} deleted")
    outcome.ok(f"deleted {kind} {key}")


# ── Helpers: payloads ───────────────────────────────────────────────────────


def _build_create_fields(
    record: dict, ctx: _Context, *, issue_type: str, parent: Optional[dict], outcome: PushOutcome,
) -> dict[str, Any]:
    """Build a Jira REST v3 `fields` payload for POST /rest/api/3/issue.

    Status is intentionally excluded — Jira always lands new issues in the project's
    default status and a separate /transitions call is required afterwards.
    """
    fields: dict[str, Any] = {
        "project": {"key": ctx.project_key},
        "issuetype": {"name": issue_type},
        "summary": (record.get("summary") or "").strip() or "(untitled)",
    }
    if record.get("priority"):
        jira_name = _resolve_priority_name(ctx, record["priority"], outcome)
        if jira_name:
            fields["priority"] = {"name": jira_name}
    if record.get("labels"):
        fields["labels"] = list(record["labels"])
    if record.get("description"):
        fields["description"] = record["description"]
    if parent:
        fields["parent"] = parent

    assignee_id = _assignee_account_id(record, ctx, outcome)
    if assignee_id:
        fields["assignee"] = {"accountId": assignee_id}

    if issue_type == "Story" and record.get("points") is not None:
        points_field = _resolve_points_field_id(ctx, outcome)
        if points_field:
            fields[points_field] = record["points"]

    return fields


def _build_update_fields(record: dict, ctx: _Context, *, outcome: PushOutcome) -> dict[str, Any]:
    """Build a PUT payload from the current local record. Status is sent separately
    via /transitions; see `_apply_transition`."""
    fields: dict[str, Any] = {"summary": (record.get("summary") or "").strip()}
    if record.get("priority"):
        jira_name = _resolve_priority_name(ctx, record["priority"], outcome)
        if jira_name:
            fields["priority"] = {"name": jira_name}
    fields["labels"] = list(record.get("labels") or [])
    if record.get("description") is not None:
        fields["description"] = record["description"]

    user = record.get("assignee") or record.get("owner")
    if user is None:
        fields["assignee"] = None
    else:
        assignee_id = _assignee_account_id(record, ctx, outcome)
        if assignee_id:
            fields["assignee"] = {"accountId": assignee_id}

    if record.get("points") is not None:
        points_field = _resolve_points_field_id(ctx, outcome)
        if points_field:
            fields[points_field] = record["points"]

    return fields


def _assignee_account_id(record: dict, ctx: _Context, outcome: PushOutcome) -> Optional[str]:
    user = record.get("assignee") or record.get("owner")
    if not isinstance(user, dict) or not user.get("email"):
        return None
    return _resolve_account_id(ctx, user["email"], outcome)


_POINTS_FIELD_NAMES = {"story points", "story point estimate"}

# Per canonical priority, the Jira display names we'll accept (case-insensitive),
# ordered by preference. The first one that exists in the tenant wins.
_PRIORITY_PREFERENCES: dict[str, tuple[str, ...]] = {
    "critical": ("highest", "critical", "blocker"),
    "high": ("high", "major"),
    "medium": ("medium", "normal"),
    "low": ("low", "minor", "lowest"),
}


def _resolve_priority_name(ctx: _Context, canonical: str, outcome: PushOutcome) -> Optional[str]:
    """Translate a canonical priority into the Jira name configured for this tenant.

    Cached for the merge. Returns None when the tenant exposes no priority that we
    can map to (uncommon — basic projects always have at least Low/Medium/High).
    """
    if not ctx.priority_map_resolved:
        ctx.priority_map_resolved = True
        try:
            priorities = ctx.client.get("/rest/api/3/priority") or []
        except JiraHTTPError:
            outcome.warn("could not list Jira priorities; priority edits will be skipped")
            return None
        available = {(p.get("name") or "").lower(): p["name"] for p in priorities}
        for canon, preferred in _PRIORITY_PREFERENCES.items():
            for candidate in preferred:
                if candidate in available:
                    ctx.priority_map[canon] = available[candidate]
                    break

    name = ctx.priority_map.get(canonical)
    if name is None:
        outcome.warn(f"no Jira priority maps to canonical {canonical!r}; field skipped")
    return name


def _resolve_points_field_id(ctx: _Context, outcome: PushOutcome) -> Optional[str]:
    """Look up the Story Points custom-field ID for this tenant, cached for the merge.

    Returns the field ID (e.g. ``customfield_10026``), or None if the project has no
    Story Points field at all (common for basic Kanban templates). In the missing
    case we warn once so the user understands why their `--points` edits no-op.
    """
    if ctx.points_field_resolved:
        return ctx.points_field_id

    ctx.points_field_resolved = True
    try:
        fields = ctx.client.get("/rest/api/3/field")
    except JiraHTTPError:
        outcome.warn("could not list Jira fields; story points will be skipped this merge")
        return None

    for f in fields or []:
        if (f.get("name") or "").lower() in _POINTS_FIELD_NAMES:
            ctx.points_field_id = f.get("id")
            return ctx.points_field_id

    outcome.warn(
        "this Jira project has no Story Points field configured; "
        "local `points` values won't be pushed"
    )
    return None


# ── Helpers: transitions, users, baselines ──────────────────────────────────


def _apply_transition(ctx: _Context, key: str, canonical_status: str, outcome: PushOutcome) -> None:
    target_name = ctx.status_map.get(canonical_status)
    if not target_name:
        outcome.warn(f"no transition mapping for canonical status {canonical_status!r}; skipped on {key}")
        return

    transitions = ctx.client.get(f"/rest/api/3/issue/{key}/transitions").get("transitions", [])
    match = next(
        (t for t in transitions if (t.get("to") or {}).get("name", "").lower() == target_name.lower()),
        None,
    )
    if match is None:
        # No path → either already in that state (Jira hides self-transitions) or the
        # workflow truly doesn't allow it. The first case is a no-op, the second is
        # surfaceable but rare; warn and move on either way.
        outcome.warn(f"{key}: no available transition lands on {target_name!r}; skipped")
        return

    ctx.client.post(
        f"/rest/api/3/issue/{key}/transitions",
        json={"transition": {"id": match["id"]}},
    )


def _transition_after_create(
    ctx: _Context, key: str, canonical_status: Optional[str], outcome: PushOutcome,
) -> None:
    """Move a freshly-created issue into the desired canonical status if it isn't already.

    Jira always lands new issues in the project's default status (typically "To Do"),
    so a `pm epic create … --status in-progress` flow needs an explicit transition
    after the POST or the local intent is silently lost.
    """
    if not canonical_status:
        return
    try:
        _apply_transition(ctx, key, canonical_status, outcome)
    except JiraHTTPError as exc:
        outcome.warn(f"{key}: created but transition to {canonical_status!r} failed: {_format_http_error(exc)}")


def _resolve_project_key(client: JiraClient, config: Config) -> str:
    """Fetch projectKey from the board if it wasn't persisted during clone."""
    if not config.board_id:
        raise PushError("config has no boardId — cannot resolve project. Run `clone` first.")
    board = client.get_board(config.board_id)
    pk = (board.get("location") or {}).get("projectKey")
    if not pk:
        raise PushError(f"could not derive project key from board {config.board_id}.")
    return pk


def _resolve_account_id(ctx: _Context, email: str, outcome: Optional[PushOutcome]) -> Optional[str]:
    """Email → accountId via /user/search, cached per merge."""
    if email in ctx.accountid_cache:
        return ctx.accountid_cache[email]
    try:
        result = ctx.client.get("/rest/api/3/user/search", params={"query": email})
    except JiraHTTPError:
        result = []
    account_id = result[0]["accountId"] if result else None
    if account_id is None and outcome is not None:
        outcome.warn(f"could not resolve account for {email}; assignee left null")
    ctx.accountid_cache[email] = account_id
    return account_id


def _baseline_record(key: str, kind: str, ctx: _Context, *, epic_key: Optional[str] = None) -> Optional[dict]:
    path = baseline_dir() / f"{key}.json"
    if not path.exists():
        return None
    raw = read_json(path)
    if kind == "epic":
        return epic_shape(raw, ctx.status_map)
    return story_shape(raw, ctx.status_map, epic_key)


def _needs_update(current: dict, baseline: Optional[dict]) -> bool:
    """Treat missing keys and None values as equivalent so older clone schemas
    (e.g. records written before `points` was tracked) don't read as 'modified'.
    """
    if baseline is None:
        return False
    return _normalize(current) != _normalize(baseline)


def _normalize(d: dict) -> dict:
    """Drop keys whose values are None or empty containers — they're equivalent to absent."""
    return {k: v for k, v in d.items() if v not in (None, [], {}, "")}


def _fetch_issue(client: JiraClient, key: str) -> Optional[dict[str, Any]]:
    try:
        return client.get_issue(key)
    except JiraHTTPError:
        return None


# ── Helpers: workspace walk ─────────────────────────────────────────────────


def _iter_epics(*, include_deleted: bool = False):
    root = epics_dir()
    if not root.exists():
        return
    for edir in sorted(root.iterdir()):
        if not edir.is_dir():
            continue
        epic_path = edir / "epic.json"
        if not epic_path.exists():
            continue
        record = read_json(epic_path)
        if not include_deleted and record.get("_deleted"):
            continue
        yield edir, record


def _iter_stories(*, skip_deleted: bool = False):
    """Yields `(story_dir, story_record, epic_dir_or_None)` for every story on disk.

    Tombstoned (`_deleted`) records are yielded by default — the delete phase needs
    them — and callers that don't want them pass `skip_deleted=True`.
    """
    def _emit(sdir: Path, edir: Optional[Path]):
        spath = sdir / "story.json"
        if not spath.exists():
            return None
        record = read_json(spath)
        if skip_deleted and record.get("_deleted"):
            return None
        return sdir, record, edir

    root = epics_dir()
    if root.exists():
        for edir in sorted(root.iterdir()):
            if not edir.is_dir():
                continue
            for sdir in sorted(edir.iterdir()):
                if not sdir.is_dir():
                    continue
                result = _emit(sdir, edir)
                if result is not None:
                    yield result

    orphans = unparented_dir()
    if orphans.exists():
        for sdir in sorted(orphans.iterdir()):
            if not sdir.is_dir():
                continue
            result = _emit(sdir, None)
            if result is not None:
                yield result


# ── Helpers: post-create local renames ──────────────────────────────────────


def _adopt_real_key(item_dir: Path, json_filename: str, old_key: str, real_key: str, ctx: _Context) -> Path:
    """Rename the item dir to the real Jira key, refresh the record file, write baseline.

    Returns the (possibly renamed) directory path.
    """
    record_path = item_dir / json_filename
    record = read_json(record_path)
    record["key"] = real_key
    record.pop("_unpushed", None)

    fetched = _fetch_issue(ctx.client, real_key)
    if fetched:
        atomic_write_json(baseline_dir() / f"{real_key}.json", fetched)
        if json_filename == "epic.json":
            record.update(epic_shape(fetched, ctx.status_map))
        else:
            record.update(story_shape(fetched, ctx.status_map, record.get("epic")))
            record["points"] = read_json(record_path).get("points")  # preserve user-set value

    atomic_write_json(record_path, record)

    new_dirname = issue_dirname(real_key, record.get("summary", ""))
    new_dir = item_dir.parent / new_dirname
    if new_dir != item_dir:
        item_dir.rename(new_dir)
        return new_dir
    return item_dir


# ── Helpers: errors, time, logging ──────────────────────────────────────────


def _format_http_error(exc: JiraHTTPError) -> str:
    body = exc.body
    if not isinstance(body, dict):
        return f"{exc.status_code} {body!s}"

    parts: list[str] = []
    for msg in body.get("errorMessages") or []:
        parts.append(str(msg))
    for fname, fmsg in (body.get("errors") or {}).items():
        parts.append(f"{fname}: {fmsg}")
    return f"{exc.status_code} {'; '.join(parts) or 'no details'}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_log(outcome: PushOutcome, config: Config) -> None:
    log_dir().mkdir(parents=True, exist_ok=True)
    stem = outcome.started_at.replace(":", "-").replace(".", "-")
    path = log_dir() / f"push-{stem}.json"
    payload = {
        "started_at": outcome.started_at,
        "finished_at": outcome.finished_at,
        "successes": outcome.successes,
        "failures": [{"item": label, "error": err} for label, err in outcome.failures],
        "warnings": outcome.warnings,
        "project_key": config.project_key,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n")
