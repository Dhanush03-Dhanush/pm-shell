---
name: pm-work
description: 'Implement a Jira story tracked in a `.jira/` workspace via the `pm` CLI — updating status as tasks complete and logging decisions/gotchas to story comments. Triggers: "implement KAN-N", "work on KAN-N", "start the story", "finish KAN-N", "mark done", "wrap up". For creating new epics/stories from scratch, use `pm-refine` instead.'
---

# pm-work

Two sections below:

1. **Core (locked)** — How to interact with `pm`. **Do not edit.**
2. **Team preferences (editable)** — Work loop, comment taxonomy, pre-merge expectations. **Edit this** to match your team.

<!-- ============================================================ -->
<!-- ===================== CORE — DO NOT EDIT ==================== -->
<!-- ============================================================ -->

## Core (locked)

> **Notice to the LLM:** Do not edit this section. It defines how you interact with `pm`. To change team conventions (comment tags, what to log, etc.), edit the **Team preferences** section below.

`pm` ("pm shell") is a git-like CLI that mirrors a Jira board into a local `.jira/` directory. You read and edit tickets locally; nothing reaches Jira until the user runs `pm merge`. Most commands are **cwd-aware** — running them inside an epic or story dir infers the key.

### Rules you must not break

1. **Never run `pm merge` unprompted.** Every push to Jira requires explicit user approval — every time, not once-per-session. When the user says "push" or "merge", summarize first, then wait for explicit go.
2. **Never edit `.jira/*.json` directly.** Always go through `pm` so `_unpushed` flags and key mappings stay correct.
3. **Never touch `.jira/.baseline/` or `.jira/config.json`.** Managed by clone/pull; `config.json` holds credentials.
4. **`pm clone --force` wipes local edits.** Suggest it only when the user wants to discard local state entirely.
5. **Don't blanket-close stories with open tasks.** If `pm done` warns about open tasks, stop and ask the user — either there's work left or those tasks should be deleted.

### Discover commands via `--help` — never assume

**Always learn the current CLI surface from `pm --help` and `pm <command> --help`.** Do not rely on commands memorized from prior sessions; the CLI evolves. If a command you expect doesn't appear in `--help`, it doesn't exist — ask the user rather than guessing flag names.

```bash
pm --help                 # top-level commands
pm task --help            # subcommands for a group
pm comment add --help     # flags + usage
```

### Before doing anything

```bash
pm --help           # learn the CLI
test -d .jira/      # confirm workspace
pm tree             # see current state
```

If `pm` isn't on `PATH`, ask the user where it's installed (a common install path is `~/.local/bin/pm`, but don't assume) — don't try to install it yourself. If `.jira/` is missing, suggest `pm clone` and stop.

### Start-of-work routine

Before writing any code, **read the story**. The three things that matter are the story description (acceptance criteria), the task list, and prior comments. Discover the exact `pm` commands via `pm --help` — `pm show` and `pm tree` are typical starting points. Past comments tagged with team-defined prefixes (see Team preferences) often save hours of re-discovery.

<!-- ============================================================ -->
<!-- ============== TEAM PREFERENCES — EDIT BELOW ================ -->
<!-- ============================================================ -->

## Team preferences (editable)

> **Edit this section** to match your team's implementation conventions. Core above defines how the LLM talks to `pm`; this defines what your team considers good during a build.

### The work loop

```
pm start                       # mark story in-progress
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

All changes stay local until the user explicitly approves `pm merge`.

### Comment taxonomy

Story comments are **persistent context for future you, your teammates, and future LLMs**. Most teams treat them as throwaway chatter; structured comments turn them into a searchable decision log.

Use these tag prefixes:

| Tag           | Use for                               |
| ------------- | ------------------------------------- |
| `[decision]`  | A choice you made and the reasoning   |
| `[constraint]`| A non-obvious limit you discovered    |
| `[gotcha]`    | Something that broke or surprised you |
| `[deferred]`  | Work skipped on purpose and why       |
| `[ref]`       | Link to PR, doc, ticket, or thread    |

**Format**: tag + 1–3 sentences + optional file/function reference. Be concrete:

```
[decision] Using lazy permission cache (resolve on first request) instead of eager — auth/permissions.py::resolve. Eager would 2x login latency for users with 20+ groups.

[constraint] Okta refresh-token TTL is 8h, not 24h as docs claim. Confirmed via test 2026-05-24.

[gotcha] Integration tests fail under Docker on M1 — needs --platform linux/amd64.

[deferred] Rate-limiting per-IP — needs Redis, not provisioned. Track separately if it ships.

[ref] PR #842 implements the callback handler. Related to KAN-99.
```

When replying to an earlier comment, reference it by author and date so the thread reads coherently:

```
[ref] Following up on @dhanush 2026-05-20: confirmed the TTL is configurable per-app via Okta admin settings.
```

### What NOT to comment

These add noise without value:

- **Narration** — "First I edited the file, then I added imports." Git already shows this.
- **Routine completion** — "Task 1 done." `pm task done 1` already records that.
- **Obvious code explanations** — "This function handles OAuth." The function name does too.
- **Status the field already shows** — Don't comment "moving to in-progress" when `pm start` did that.
- **Speculation without basis** — "This might be slow." Either measure or skip.

A comment is worth writing only if a future reader (human or LLM) would benefit. If you'd skim past it on a re-read, don't write it.

### During the work

- **Updating fields.** When priority or scope shifts mid-implementation, update the story — don't silently power through. On a scope change, also add a `[decision]` comment so future readers see *why* the field changed.
- **Scope creep.** New subtasks emerge. *Same-story* (edge case you didn't anticipate): add a task and continue. *New-story* ("while looking at this I realized we also need X"): don't silently expand — surface it to the user and ask whether to add a task, spin up a new story (handoff to `pm-refine`), or note it as `[deferred]`.
- **Blocking.** If you genuinely cannot proceed, block the story with an explanatory message. Reserve for true blockers, not "waiting on a quick review."

### Closing out

- **Close via `pm done`.** If it warns about open tasks, stop and ask — don't blanket-close.
- **Optional wrap-up.** Leave a `[ref]` comment summarizing the implementation and pointing at the merged PR.
- **Pre-merge summary.** When the user says "push" or "merge", show `pm status` and summarize in plain text:
  > "About to push: status change on KAN-5 → done, 4 task completions, 2 comments. Want me to run `pm merge`, or adjust first?"

  Wait for explicit go.
