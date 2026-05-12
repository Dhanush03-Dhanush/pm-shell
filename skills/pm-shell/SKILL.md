---
name: pm-shell
description: Use when the workspace contains a `.jira/` directory or the user references Jira items (KAN-N / PROJ-N style keys, "stories", "epics", "sprints", "refine", "the board"). Drives the `pm` CLI to read the local Jira mirror, mark tasks/stories done as work progresses, log comments, create new epics/stories during refinement, and push changes back to Jira via `pm merge`.
---

# pm-shell

The `pm` CLI is a git-style shell for a local Jira mirror. A repo with `.jira/` at its root has Jira state checked out as JSON files (epics, stories, tasks, comments). All edits are local until `pm merge` pushes them to Jira.

This skill tells you how to detect that workspace and which `pm` commands to use for common flows. Direct edits to `.jira/*.json` work but skip the `_unpushed` / status-mapping bookkeeping — **prefer `pm` commands**.

## When this skill applies

- A `.jira/` directory exists at the repo root (or a parent of cwd — `pm` walks up to find it).
- The user mentions Jira issues by key (uppercase letters + dash + number, e.g. `KAN-5`).
- The user asks to refine, plan, estimate, or update tickets.
- The user is finishing implementation and wants to mark tasks done / push state.

If `.jira/` is missing AND the user is asking generally about a Jira board, you can suggest `pm config init` then `pm clone` to set one up; otherwise this skill doesn't apply.

## Quick orientation

```bash
test -d .jira/ && which pm        # both should succeed
pm tree                            # whole workspace tree
pm status                          # what's locally dirty / unpushed
```

If `pm` isn't on PATH, the install lives at `~/.local/bin/pm` (via `uv tool install --editable .` from the pm-shell repo). Tell the user; don't try to install it yourself.

## Reading state

You can read the JSON files directly or use `pm` — direct reads are fine for *context*, `pm` is preferred when rendering for the user.

| Goal | Command (or file) |
| --- | --- |
| Acceptance criteria for a story | `cat .jira/epics/<EPIC>_*/<STORY>_*/story.json` (look at `description`) |
| Subtask breakdown | `cat .jira/epics/<EPIC>_*/<STORY>_*/tasks.json` |
| Existing comments / decisions | `cat .jira/epics/<EPIC>_*/<STORY>_*/comments.json` |
| Visual card for the user | `pm story show KAN-5` or `pm epic show KAN-4` |
| All epics | `pm epic list` |
| Local changes pending push | `pm status` (and `pm diff` for unified diffs) |

The dir-name format is `<KEY>_<slug>/` — extract just the key when needed (`KAN-5_sso-integration` → `KAN-5`).

## Doing work — preferred commands

**Always run from inside the relevant directory when possible** — `pm` infers epic/story keys from cwd, so commands like `pm task done 2` work without typing the key. Use `cd .jira/epics/KAN-4_*/KAN-5_*` to drop into a story.

```bash
# Mark a task complete as you finish each subtask
pm task done 2

# Mark a task reopened
pm task undone 2

# Add a task that surfaces during implementation
pm task add "Wire OAuth callback edge case"

# Move a story through workflow states (cwd-inferred)
pm start                       # → in-progress
pm done                        # → done (warns if open subtasks)
pm block "Waiting on tenant"   # → blocked + appends a comment

# Set fields explicitly with full key
pm story set KAN-5 --status in-progress --priority high --points 5
pm epic set KAN-4 --priority critical --label backend

# Log a working comment (gets posted on merge)
pm comment add "Implemented OAuth happy path; refresh-token flow next."
```

These changes stay **local** (the records get `_unpushed: true` markers). The user controls when they reach Jira via `pm merge`.

## Refinement — creating new epics/stories from discussion

When the user is planning and says things like "let's create an epic for X" or "spin up a story for Y":

```bash
pm epic create "Auth overhaul" --priority high --label security
# → NEW-1 placeholder, lives at .jira/epics/NEW-1_auth-overhaul/

pm story create "SSO integration" --epic KAN-4 --priority high --points 5
# → NEW-2 under KAN-4

pm story create "Welcome screen"   # auto-links to epic if cwd is inside one
```

If the user describes acceptance criteria for the story, capture them with `--description "..."` or after creation with `pm story set <KEY> --description "..."` (single-line) or `pm story edit <KEY>` (opens $EDITOR — only when interactive).

For subtasks, after creating the story `cd` into it and `pm task add "..."` once per subtask.

The `NEW-N` placeholder keys get replaced with real Jira keys when the user runs `pm merge`.

## Syncing to Jira

`pm merge` pushes everything dirty. **Never run merge unprompted** — it touches real Jira issues and there is no undo. The right flow:

```bash
pm status                  # show the user what's local
pm diff                    # show specific changes (TUI viewer in shell, inline in one-shot)
pm merge --dry-run         # preview the API calls
pm merge                   # asks "Apply these changes to Jira?" — Yes/No
pm merge --yes             # bypass prompt (only when the user has explicitly approved)
```

After merge succeeds, local placeholders (`NEW-1`) become real keys (`KAN-99`), `_unpushed` markers clear, and a log entry is written to `.jira/.log/push-<timestamp>.json`.

## Code + Jira together

When implementing a story alongside code in the same repo:

1. Read `story.json` (acceptance criteria) and `tasks.json` (subtask checklist).
2. Implement code. As you finish each subtask, `cd` into the story dir and `pm task done N`.
3. When the whole story is done, `pm done` (still in the story dir) — it warns if any tasks remain open.
4. Optionally `pm comment add "Implementation notes: ..."` to leave a trail.
5. Hand control back to the user. **Don't auto-merge.** Ask whether to push code (`git push`) and/or Jira state (`pm merge`) — they're independent operations and the user usually wants them separately.

## Safety rules

1. **Never run `pm merge` without an explicit user request.** Local edits are reversible; `pm merge` is not.
2. **Prefer `pm` commands over editing `.jira/*.json` directly.** The CLI maintains `_unpushed` flags, status mappings, and renumbers task IDs.
3. **`pm block` may error** if the project workflow has no Blocked status — that's correct behavior. Suggest the user add a Blocked status in Jira or use `pm story set --status <whatever-they-have>`.
4. **Don't touch `.jira/.baseline/` or `.jira/config.json`** — those are managed by `pm clone` / `pm pull` and store credentials.
5. **`pm clone --force` wipes local edits.** Suggest it only when the user wants to discard local state entirely.

## Examples

### Refining a new feature with the user

> User: "We need to plan auth migration. Make me an epic with stories for SSO, session refresh, and metrics."

```bash
pm epic create "Auth migration" --priority high --label auth
# → NEW-1
pm story create "SSO integration" --epic NEW-1 --priority high --points 5
pm story create "Session refresh" --epic NEW-1 --priority medium --points 3
pm story create "Auth metrics + alerts" --epic NEW-1 --priority low --points 2
pm tree
```

Then show the user what was scaffolded and ask about subtasks.

### Implementing a story end-to-end

```bash
cd .jira/epics/KAN-4_auth-overhaul/KAN-5_sso-integration
cat story.json | jq -r .description    # read acceptance criteria
pm task list                           # see the subtasks
pm start                               # status → in-progress

# ... write code, run tests ...
pm task done 1
pm task done 2

pm comment add "All subtasks complete; PR opened against develop."
pm done                                # story → done

# Now hand off; ask the user about push.
```

### Just adjusting fields

```bash
pm story set KAN-5 --priority critical --assignee dhanush@example.com --points 8
pm story show KAN-5
```

## Reference

- `pm help` inside the shell prints the full flag list for every command.
- `pm <command> --help` works on the one-shot CLI form.
- Workspace layout and spec live in the pm-shell repo (`docs/jira-shell-spec.docx`).
