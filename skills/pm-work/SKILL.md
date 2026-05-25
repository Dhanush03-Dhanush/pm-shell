---
name: pm-work
description: Use when implementing a Jira story — when the user says "implement KAN-N", "work on KAN-N", "start the story", "I'm done with KAN-N", or when writing code that maps to a specific ticket. Updates story/task status as work progresses and logs important context (decisions, constraints, gotchas) to story comments. Triggers include "implement [KEY]", "work on [KEY]", "start [KEY]", "finish [KEY]", "mark done", "wrap up [KEY]". Requires a `.jira/` workspace at the repo root or a parent dir. For creating new epics/stories/tasks from scratch, use the `pm-refine` skill instead.
---

# pm-work

Use this skill to **implement work that's already scaffolded** — read story state, update status as tasks complete, and log context to comments that will be useful months from now.

This skill is for *changing state on existing tickets*. For creating new structure, use `pm-refine`.

## Workspace check

```bash
test -d .jira/ && which pm
```

If `pm` isn't on PATH it lives at `~/.local/bin/pm` — tell the user; don't try to install it yourself.

## Start-of-work routine

Before writing any code, **read the story**. Three files:

```bash
cd .jira/epics/<EPIC>_*/<STORY>_*     # cwd-aware: subsequent commands infer the key

cat story.json | jq '.description'     # acceptance criteria
cat tasks.json                          # subtask checklist
cat comments.json                       # prior decisions & context
```

The comments file is the most under-used. Past comments tagged `[decision]` or `[gotcha]` often save hours of re-discovery.

## The work loop

```bash
pm start                       # status → in-progress
# ... implement task 1 ...
pm task done 1
# ... implement task 2; discover an edge case ...
pm task add "Handle expired refresh tokens"
pm comment add "[decision] JWT over session cookies — mobile clients need stateless auth."
pm task done 2
pm task done 3                 # the new task you added
# ... story complete ...
pm done                        # warns if any tasks remain open
```

All changes stay local. **Never run `pm merge` without explicit user approval.**

## Comment taxonomy

Story comments are **persistent context for future you, your teammates, and future LLMs**. Most teams treat them as throwaway chatter; structured comments turn them into a searchable decision log.

Use these tag prefixes:

| Tag | Use for | Example |
|---|---|---|
| `[decision]` | A choice you made and the reasoning | `[decision] JWT over session cookies — mobile clients need stateless auth. Cookies can be revisited if web-only ever ships.` |
| `[constraint]` | A non-obvious limit you discovered | `[constraint] Okta refresh-token TTL is 8h, not 24h as docs claim. Confirmed via test 2026-05-24.` |
| `[gotcha]` | Something that broke or surprised you | `[gotcha] Integration tests fail under Docker on M1 — needs --platform linux/amd64.` |
| `[deferred]` | Work skipped on purpose and why | `[deferred] Rate-limiting per-IP — needs Redis, not provisioned. Tracked separately if it ships.` |
| `[ref]` | Link to PR, doc, ticket, or thread | `[ref] PR #842 implements the callback handler. Related to KAN-99.` |

**Format**: tag + 1–3 sentences + optional file/function reference. Be concrete:

```bash
pm comment add "[decision] Using lazy permission cache (resolve on first request) instead of eager — auth/permissions.py::resolve. Eager would 2x login latency for users with 20+ groups."
```

When replying to an earlier comment, reference it by author and date so the thread reads coherently:

```bash
pm comment add "[ref] Following up on @dhanush 2026-05-20: confirmed the TTL is configurable per-app via Okta admin settings."
```

## What NOT to comment

These add noise without value:

- **Narration** — "First I edited the file, then I added imports." Git already shows this.
- **Routine completion** — "Task 1 done." `pm task done 1` already records that.
- **Obvious code explanations** — "This function handles OAuth." The function name does too.
- **Status the field already shows** — Don't comment "moving to in-progress" when `pm start` did that.
- **Speculation without basis** — "This might be slow." Either measure or skip.

A comment is worth writing only if a future reader (human or LLM) would benefit from seeing it. If you'd skim past it on a re-read, don't write it.

## Updating fields during work

When scope or priority shifts mid-implementation, update the story — don't silently power through:

```bash
pm story set --priority critical                # cwd-inferred
pm story set --points 8                          # was 5; work was bigger than expected
```

If the user explicitly changes scope, also add a `[decision]` comment explaining why so future readers understand the field change.

## Surfacing scope creep

New subtasks emerge mid-implementation. Two cases:

- **Same-story scope** (e.g., an edge case you didn't anticipate): `pm task add "..."` and keep going.
- **New-story scope** (e.g., "while looking at this I realized we also need X"): **don't silently expand**. Tell the user and ask whether to add a task here, create a new story (handoff to `pm-refine`), or just note it as a `[deferred]` comment.

## Blocking

```bash
pm block "Waiting on Okta admin to provision the app"
```

Sets the story to `blocked` and appends an explanatory comment automatically. Use only when you genuinely cannot proceed.

## Closing the story

```bash
pm done                        # cwd-aware; warns if open tasks remain
```

If `pm done` warns about open tasks, **stop and ask the user** — don't blanket-close. Either there's remaining work or those tasks should be deleted.

Optionally, leave a wrap-up comment summarizing the implementation:

```bash
pm comment add "[ref] PR #842 merged. Tasks 1–4 complete; task 5 deferred to KAN-101 per scope discussion 2026-05-24."
```

## Pre-merge summary

When the user says "push" or "merge", **summarize first** before running anything:

```bash
pm status                      # show what's dirty
```

Then in plain text: "About to push: status change on KAN-5 → done, 4 task completions, 2 comments. Want me to run `pm merge`, or adjust first?" Wait for explicit go.

## Safety rules

1. **Never run `pm merge` unprompted.** Merge is not undoable.
2. **Prefer `pm` commands over editing `.jira/*.json` directly.** The CLI maintains `_unpushed` flags and status mappings.
3. **Don't touch `.jira/.baseline/` or `.jira/config.json`.** Managed by clone/pull; the config contains credentials.
4. **`pm clone --force` wipes local edits.** Suggest only when the user wants to discard local state entirely.

## Handoff to refinement

If the user shifts from implementing to planning new work mid-session, the `pm-refine` skill takes over.
