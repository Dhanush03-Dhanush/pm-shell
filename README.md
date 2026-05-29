# pm-shell

**A git-like shell for Jira boards.** Clone a board into `.jira/`, edit it like source code, review with `status`/`diff`, push back with `merge`.

```bash
pm clone                          # mirror the board into .jira/
pm story set KAN-5 --status done  # edit locally
pm diff                           # review what's changed
pm merge                          # push to Jira (asks first)
```

Jira state becomes **files you can read, edit, version, and review** — just like your code.

---

## Why

- **Stay in the terminal.** `cd` into an epic, mark tasks done, edit descriptions in `$EDITOR` — no browser context switch.
- **Commit tickets next to code.** A PR can show both kinds of change side-by-side.
- **AI-native.** A bundled [Claude Code](https://claude.com/claude-code) skill lets Claude read state, propose edits, and stage them locally (push stays manual).

---

## Install

```bash
git clone <this-repo> pm-shell
cd pm-shell
./install.sh
```

`install.sh` is idempotent and:

1. Ensures [uv](https://docs.astral.sh/uv/) and Python ≥3.11 are present (offers to install uv).
2. Runs `uv tool install .` so `pm` works from any directory. Pass `--dev` for an editable install.
3. Prompts for your Jira `baseUrl`, `email`, and API token, writes them to `~/.config/pm-shell/secrets.json` (chmod 600).

Get an API token at <https://id.atlassian.com/manage-profile/security/api-tokens>. If `pm` isn't on your PATH, run `uv tool update-shell` and open a new terminal.

---

## Setup

Credentials are global. Each Jira project is a **space**, registered once. Each space can be mirrored into as many local workspaces as you want.

### Create a space (once per project)

```bash
pm create                                  # interactive
pm create --name "AI Board" --key AI       # or flagged
```

This ensures a tenant-wide `Story Points` field exists, creates a team-managed Scrum project, and records the `name → boardId` mapping in `~/.config/pm-shell/spaces.json`. The Story-Points step needs Jira-admin permission; without it `pm create` fails cleanly rather than half-creating anything.

```bash
pm spaces                                  # list registered spaces
```

### Mirror a space into a workspace (repeatable)

```bash
cd ~/code/my-service
pm clone --space "AI Board"
pm                                         # open the interactive shell
```

> ⚠ No merge-conflict detection — last-write-wins. Treat multiple workspaces against the same space as serial, not concurrent.

### Alternative — point at an existing Jira board

```bash
cd ~/code/some-project
cat > jira-secrets.json <<'EOF'
{ "baseUrl": "...", "email": "...", "apiToken": "...", "boardId": 7 }
EOF
pm config init --from jira-secrets.json && rm jira-secrets.json
pm clone
```

`merge` auto-detects issue types, priority map, and the Story Points field. A project lacking an issue type literally named `Story` is the main rough edge today — see [Known limits](#known-limits).

---

## Workflows

### Refinement — plan an epic, push when agreed

```text
$ pm
~ > epic create "Authentication overhaul" --priority high --label auth
+ NEW-1: Authentication overhaul   (unpushed)

~ > cd NEW-1
NEW-1 > story create "SSO integration" --points 5
NEW-1 > story create "Session refresh" --points 3
NEW-1 > cd NEW-2
NEW-1/NEW-2 > task add "Wire OAuth callback (Okta)"
NEW-1/NEW-2 > edit                         # opens $EDITOR for the description

NEW-1/NEW-2 > diff                         # review what would push
NEW-1/NEW-2 > merge                        # Yes/No modal; on Yes, pushes
```

Local placeholder keys (`NEW-1`, ...) become real Jira keys after `merge`. Directory names and child references update automatically.

### Implementation — code and tickets in lockstep

Commit `.jira/` into the same repo as your code. Now a PR shows both diffs together.

```bash
cd my-project/
pm clone                                   # writes .jira/ at the repo root
echo ".jira/config.json" >> .gitignore     # contains your token
git add .jira/ && git commit -m "Mirror board"
```

```bash
$ pm story show KAN-5
$ cd .jira/epics/KAN-4_*/KAN-5_*           # cwd-aware: commands infer the key
$ pm start                                 # status → in-progress
$ pm task done 1
$ pm comment add "Refresh-token flow WIP."
$ pm done                                  # warns if subtasks are open
```

Commit code + ticket changes together. After review:

```bash
$ pm status
~ modified  KAN-5/story.json    SSO integration
~ modified  KAN-5/tasks.json    +2 modified

$ pm merge
```

---

## Shell modes

| Mode | Command | When to use |
|---|---|---|
| One-shot | `pm story show KAN-5` | Scripts, CI, ad-hoc |
| Interactive (Textual TUI) | `pm` (no args) | Daily use |
| Lightweight REPL | `pm shell --simple` | Pipes, non-TTY, or if Textual misbehaves |

The TUI has cwd-aware prompt (`KAN-4/KAN-5 ›`), tab-complete for commands and Jira keys, history, a modal diff viewer, and a Yes/No `merge` confirmation.

---

## Command reference

Every command supports `--help`. Inside the shell, `help` prints everything.

**Navigate**

| Command | What |
|---|---|
| `ls` | Smart list — epics at root, stories inside an epic, tasks inside a story |
| `tree [KEY\|path]` | Annotated tree |
| `show` | Card for the current epic/story (cwd-inferred) |
| `cd KEY` / `cd ..` | Jump by Jira key / up one level |

**View**

| Command | What |
|---|---|
| `epic list` / `epic show KEY` | Epics — table / card |
| `story list [--epic KEY]` / `story show KEY` | Stories — table / card |
| `task list [KEY]` | Subtask table |
| `comment list [KEY]` / `comment last [KEY]` | Comments — all / latest |

**Edit**

| Command | What |
|---|---|
| `epic set [KEY] --status --priority --summary --owner --label --description` | Update epic |
| `story set [KEY] --status --priority --summary --assignee --label --description --epic --points` | Update story |
| `set` | Routes to `epic set` or `story set` from cwd |
| `start` / `done` / `block "reason"` | Story status shortcuts |
| `edit` | `$EDITOR` on current epic/story description |
| `task add "..."` / `task done N` / `task undone N` / `task edit N "..."` / `task delete N` | Subtask ops (1-indexed) |
| `comment add "..."` | Append comment (no arg → `$EDITOR`) |

**Create**

| Command | What |
|---|---|
| `epic create "Summary" [--priority --owner --label --description]` | New epic (key `NEW-N`) |
| `story create "Summary" [--epic --priority --assignee --label --description --points]` | New story; auto-links to current epic |
| `task add "..."` | New subtask under current story |

**Delete**

| Command | What |
|---|---|
| `epic delete [KEY]` | Soft-mark; cascades to child stories. Unpushed items removed immediately |
| `story delete [KEY]` | Soft-mark a story |
| `task delete N` | Remove (subtask deleted on next `merge`) |
| `epic undelete` / `story undelete` | Clear the mark |

**Sync**

| Command | What |
|---|---|
| `pm clone [--force]` | Mirror the board into `.jira/` |
| `pm status` | Grouped table of every dirty file |
| `pm diff [KEY]` | Unified diff (modal in TUI) |
| `pm merge [--yes] [--dry-run]` | Push local changes; confirms first |

---

## Claude Code skills

Two skills under [`skills/`](skills/) drive `pm` for Claude Code:

- [`pm-refine`](skills/pm-refine/SKILL.md) — planning: scaffolds epics/stories/tasks.
- [`pm-work`](skills/pm-work/SKILL.md) — implementation: status updates, structured comments, pre-merge summaries.

```bash
mkdir -p ~/.claude/skills/pm-refine ~/.claude/skills/pm-work
cp skills/pm-refine/SKILL.md ~/.claude/skills/pm-refine/SKILL.md
cp skills/pm-work/SKILL.md   ~/.claude/skills/pm-work/SKILL.md
```

Each `SKILL.md` is split into a locked **Core** (how to interact with `pm`) and an editable **Team preferences** section (your team's conventions). Both skills **never run `pm merge` unprompted** — push to Jira always requires explicit user approval. See [`skills/README.md`](skills/README.md) for details.

---

## Workspace layout

```
.jira/
  config.json              # creds + board state (chmod 600 — gitignore this)
  epics/<KEY>_<slug>/
    epic.json
    <STORY_KEY>_<slug>/
      story.json
      tasks.json           # [{id, key, title, done, status, _unpushed?}]
      comments.json        # [{id, author, body (ADF), _unpushed?}]
  unparented/              # stories without an epic
  .baseline/<KEY>.json     # raw Jira from last clone — diffed against current
  .log/push-<ts>.json      # merge history
```

`_unpushed: true` marks new local records; `_deleted: true` marks records pending deletion. All writes are atomic.

---

## Known limits

- **No conflict detection on `merge`** — last-write-wins. Solo workspaces only.
- **Subtask edits / deletes** don't push. Only new subtasks are created.
- **Assignee resolution** uses Jira's `/user/search`; unmatched emails are sent as `null` with a warning.
- **Story Points** field is auto-detected on push. Boards without it skip the field with a warning instead of failing.
- **Issue types** are project-specific. A project without one literally named `Story` is the main rough edge today.
- **Priority round-trip** for non-canonical values (e.g. `Highest`) is skipped with a warning.
- **`pm pull`** (incremental refresh) isn't built. Re-sync with `pm clone --force` (wipes unpushed edits).

---

## Development

```bash
git clone <this-repo> && cd pm-shell
uv sync
uv tool install --editable .       # global `pm` tracks your source
uv run pm --version
```

---

## License

[MIT](LICENSE).
