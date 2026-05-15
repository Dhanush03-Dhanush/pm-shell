# pm-shell

**A git-like shell for Jira boards.** Clone the board into a local `.jira/` directory, edit it like source code, review changes with `status` and `diff`, and push back to Jira with `merge`.

```bash
pm clone                          # mirror the board into .jira/
pm story set KAN-5 --status done  # edit locally
pm diff                           # review what's changed
pm merge                          # push to Jira (asks first)
```

The whole point: Jira state becomes **files you can read, edit, version, and review** — just like your code.

---

## Why

PM tools live in browser UIs that don't compose with your terminal, your editor, your AI assistant, your git history, or your CI. pm-shell makes the project state a first-class artifact in your codebase:

- **You** stay in the terminal — `cd` into an epic, mark tasks done, edit a description in `$EDITOR`, all without context-switching.
- **Claude Code** can read story state, propose changes, and stage them locally — see [the bundled skill](#the-claude-code-skill).
- **PRs** can include both code and ticket changes together (commit `.jira/` next to `src/`).

---

## Install

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone <this-repo> pm-shell
cd pm-shell
uv tool install --editable .         # installs `pm` into ~/.local/bin
```

If you don't see `pm` on your PATH after the install, run `uv tool update-shell` and open a new terminal.

### First-time setup

Setup is three things, done at three different cadences:

| Step | Command | When |
|---|---|---|
| 1. Save credentials globally | hand-edit `~/.config/pm-shell/secrets.json` | **Once per machine.** |
| 2. Create a Jira project ("space") | `pm create` | **Once per project**, ever. Registers it in `~/.config/pm-shell/spaces.json`. |
| 3. Mirror a space into a local workspace | `pm clone --space "<name>"` | **As many times as you want**, in any directory. |

Get a Jira API token first at <https://id.atlassian.com/manage-profile/security/api-tokens>.

#### 1. Save credentials globally (once per machine)

```bash
mkdir -p ~/.config/pm-shell
cat > ~/.config/pm-shell/secrets.json <<'EOF'
{
  "baseUrl":  "https://your-tenant.atlassian.net",
  "email":    "you@example.com",
  "apiToken": "<paste-your-token>"
}
EOF
chmod 600 ~/.config/pm-shell/secrets.json
```

This file is read by `pm create` and `pm clone --space`. You write it once, then forget about it — no per-workspace secrets file needed anywhere.

#### 2. Create a Jira project (once per project)

```bash
pm create
# Space name: AI Board
# Project key (2–10 uppercase letters/digits): AI
```

What this does:

1. Ensures a tenant-wide `Story Points` number custom field exists (creates it the first time you run `pm create`, no-ops thereafter). This is a one-time per-tenant action; once it's there, every team-managed project — including the one we're about to create — gets it automatically.
2. POSTs `/rest/api/3/project` with the team-managed Scrum template, so the project comes pre-loaded with `Epic / Story / Task / Subtask` issue types, `Highest..Lowest` priorities, and the `To Do / In Progress / Done` workflow.
3. Records the resulting `{name → boardId, projectKey}` mapping in `~/.config/pm-shell/spaces.json`.

The Story-Points step needs Jira-admin permission. If your account doesn't have it, `pm create` fails with a clear pointer at the Jira UI path you'd need to use instead — no half-created project gets left behind.

You can also pass flags non-interactively:

```bash
pm create --name "AI Board" --key AI --description "AI-team work"
```

To see what's registered:

```bash
pm spaces
# NAME       KEY  BOARD ID  CREATED
# AI Board   AI   42        2026-05-14T23:55:11
# Ops        OPS  56        2026-05-15T01:02:08
```

#### 3. Mirror a space into a workspace (repeatable)

```bash
cd ~/code/my-ai-service
pm clone --space "AI Board"
pm                              # open the interactive shell
```

`pm clone --space "AI Board"` looks up the boardId in `~/.config/pm-shell/spaces.json`, writes `.jira/config.json` in the current directory by combining the global secrets with that space's `boardId`/`projectKey`, then clones. Repeat in as many directories as you want — each one is an independent local mirror, and they all push to the same Jira space on `pm merge`.

> ⚠ pm-shell has no merge-conflict detection — last-write-wins. If you maintain two workspaces against the same space, treat them as serial (push-then-`pm clone --force` elsewhere), not concurrent.

#### Alternative — point at an existing Jira board

If you already have a Jira board outside this flow (your team's, or a project somebody else created):

```bash
cd ~/code/some-project
cat > jira-secrets.json <<'EOF'
{ "baseUrl": "...", "email": "...", "apiToken": "...", "boardId": 7 }
EOF
pm config init --from jira-secrets.json && rm jira-secrets.json
pm clone
```

`pm merge` auto-detects the project's issue-type names, priority map, and Story Points field on push, so existing boards work — but a project lacking an issue type literally named `Story` is the main rough edge today (see Known limits).

---

## Two flagship workflows

### 1. Backlog refinement

You're planning, not coding. You want to spin up an epic and several stories with acceptance criteria, then push them to Jira when the team agrees.

```bash
# Open the shell — single column, prompt at the bottom, output above
pm
```

Inside the shell:

```text
~ > epic create "Authentication overhaul" --priority high --label auth
+ NEW-1: Authentication overhaul   (unpushed — run `push` to create in Jira)

~ > cd NEW-1
NEW-1 > story create "SSO integration" --priority high --points 5
+ NEW-2: SSO integration under NEW-1
NEW-1 > story create "Session refresh" --points 3
+ NEW-3: Session refresh under NEW-1
NEW-1 > story create "Auth metrics + alerts" --points 2
+ NEW-4: Auth metrics + alerts under NEW-1

NEW-1 > cd NEW-2
NEW-1/NEW-2 > task add "Wire OAuth callback (Okta)"
NEW-1/NEW-2 > task add "Add session persistence"
NEW-1/NEW-2 > task add "Token refresh job"
NEW-1/NEW-2 > edit                                # opens $EDITOR for the description

NEW-1/NEW-2 > tree NEW-1                          # review what we built
NEW-1  Authentication overhaul  todo  high
├── NEW-2  SSO integration  todo  0/3
│   ├── · NEW-2  Wire OAuth callback (Okta)
│   ├── · NEW-2  Add session persistence
│   └── · NEW-2  Token refresh job
├── NEW-3  Session refresh  todo  0/0
└── NEW-4  Auth metrics + alerts  todo  0/0
```

Local placeholder keys (`NEW-1`, `NEW-2`, ...) stand in until you push. Nothing has touched Jira yet. To review what would happen on push:

```text
NEW-1/NEW-2 > status                              # summary of dirty items
NEW-1/NEW-2 > diff                                # opens the diff viewer (Esc to return)
NEW-1/NEW-2 > merge --dry-run                     # preview API calls without contacting Jira
NEW-1/NEW-2 > merge                               # opens a Yes/No modal; on Yes, pushes to Jira
```

After `merge` succeeds, every `NEW-N` placeholder is replaced with a real Jira key (e.g. `KAN-99`), directories are renamed, child refs are rewritten, and an entry is written to `.jira/.log/push-<timestamp>.json`.

**No code repo required.** This flow works in any directory with a `.jira/` mirror.

---

### 2. Code and tickets in lockstep

The bigger idea: **commit `.jira/` into the same git repo as your code.** Now your PR shows both kinds of change side-by-side.

#### Setup

```bash
cd my-project/
pm config init --from /path/to/jira-secrets.json
pm clone                       # writes .jira/ at the repo root
git add .jira/
git commit -m "Mirror Jira board into repo"
```

`.jira/config.json` is `chmod 600` and contains your API token — add `.jira/config.json` to `.gitignore` (the contents of `.jira/epics/` and `.jira/.baseline/` are fine to commit).

#### Implementing a story

```bash
# 1. Find the story
$ pm story show KAN-5
╭─ KAN-5  SSO integration ───────────────────────────╮
│ Status   in-progress                                │
│ Priority high                                       │
│ Points   5                                          │
│ Tasks    0/3 done                                   │
│                                                     │
│ Description                                         │
│ Wire Okta SAML against the new auth gateway.        │
╰─────────────────────────────────────────────────────╯

# 2. cd into the story; commands now infer the key from cwd
$ cd .jira/epics/KAN-4_auth-overhaul/KAN-5_sso-integration
$ pm start                                # status → in-progress
$ pm task list
1 · Wire OAuth callback (Okta)            KAN-6
2 · Add session persistence               KAN-7
3 · Token refresh job                     KAN-8

# 3. Implement code. As each subtask completes, mark it done.
$ pm task done 1
$ pm task done 2
$ pm comment add "Refresh-token flow still WIP."

# 4. When the story is done:
$ pm done                                 # warns if subtasks remain open
```

#### Commit + PR — code and ticket changes together

```bash
$ git status
modified:   src/auth/oauth.py
modified:   src/auth/session.py
modified:   .jira/epics/KAN-4_auth-overhaul/KAN-5_sso-integration/story.json
modified:   .jira/epics/KAN-4_auth-overhaul/KAN-5_sso-integration/tasks.json
modified:   .jira/epics/KAN-4_auth-overhaul/KAN-5_sso-integration/comments.json

$ git commit -am "KAN-5: implement OAuth callback and session persistence"
$ git push  # PR opens — reviewer sees both code and ticket diffs
```

In review, your teammate can run `pm diff` against the branch to see the structured ticket changes (status `in-progress → done`, tasks 1/2 flipped, new comment) alongside the code diff. After the PR merges, push the ticket state to Jira:

```bash
$ pm status
~ modified  KAN-5/story.json    SSO integration
~ modified  KAN-5/tasks.json    +2 modified
+ created   KAN-5/comments.json +1 unpushed comment(s)

$ pm merge          # confirms first; on Yes, applies to Jira and refreshes baselines
```

Code and tickets stay in sync. Audit history is in git.

---

## The Claude Code skill

This repo ships a [Claude Code](https://claude.com/claude-code) skill that teaches Claude how to drive `pm` for both workflows above. Once installed, Claude detects `.jira/` workspaces and uses the CLI to read state, mark tasks done as it works, log comments, scaffold epics during refinement, and (only when you ask) push via `pm merge`.

### Install the skill

```bash
mkdir -p ~/.claude/skills/pm-shell
cp skills/pm-shell/SKILL.md ~/.claude/skills/pm-shell/SKILL.md
```

That's it. Claude picks the skill up automatically on the next session.

For per-project install instead of global, drop the file at `<your-repo>/.claude/skills/pm-shell/SKILL.md`.

### What it does — concrete agent flows

#### Refinement with Claude

> **You:** "Let's plan a refactor of our logging stack. Make me an epic with stories for structlog migration, OpenTelemetry adoption, and per-service log volume targets."

Claude will run:

```bash
pm epic create "Logging refactor" --priority high --label observability
pm story create "Migrate to structlog" --epic NEW-1 --points 5
pm story create "Adopt OpenTelemetry"  --epic NEW-1 --points 8
pm story create "Define per-service log volume targets" --epic NEW-1 --points 3
pm tree NEW-1
```

Then it'll show you the tree and ask whether you want to add subtasks or acceptance criteria. Nothing reaches Jira until you say `pm merge`.

#### Implementation with Claude

> **You:** "Implement KAN-5."

Claude will:

1. Read `.jira/epics/KAN-4_*/KAN-5_*/story.json` for the acceptance criteria.
2. Read `tasks.json` for the subtask checklist.
3. `cd` into the story dir and run `pm start`.
4. Write code, run tests.
5. After each subtask is done, run `pm task done N`.
6. Add a `pm comment add "..."` summarizing the implementation.
7. When everything's complete, run `pm done`.
8. Hand control back. **It will not push to Jira without explicit instruction.**

### Safety rules baked into the skill

- `pm merge` is never run unprompted. Local edits are reversible; merge is not.
- `pm` commands are preferred over editing `.jira/*.json` directly (keeps `_unpushed` flags and status mappings correct).
- `.jira/config.json` and `.jira/.baseline/` are off-limits to Claude (they're managed by `clone`/`pull`).
- `pm clone --force` discards local edits — Claude only suggests it when you want to start over.

Full skill body: [`skills/pm-shell/SKILL.md`](skills/pm-shell/SKILL.md).

---

## Interactive shell vs. one-shot CLI

Every command works two ways:

| Mode | Command | When to use |
|---|---|---|
| One-shot | `pm story show KAN-5` | Scripts, CI, ad-hoc lookup |
| Interactive shell | `pm` (no args) | Daily use, multiple commands in a session |
| Lightweight REPL | `pm shell --simple` | Pipes, non-TTY, or if Textual misbehaves |

The interactive shell is a Textual TUI with:

- Persistent prompt with cwd-aware context label (`KAN-4/KAN-5 ›`)
- Tab-complete for commands and Jira keys (scoped to the current dir — root shows epics, inside an epic shows that epic's stories)
- ↑/↓ command history, PgUp/PgDn scroll output, Ctrl-L clear, Ctrl-D quit
- `diff` opens a modal with a file list on the left and a green/red unified diff on the right; ↑/↓ navigate, Esc returns
- `merge` opens a Yes/No confirmation modal before doing anything

---

## Command reference

Every command supports `--help`. Inside the shell, `help` prints the full flag list for everything.

### Browse / navigate

| Command | What it does |
|---|---|
| `ls` | Smart listing: epic table at root, story table inside an epic, tasks inside a story |
| `tree [KEY\|path]` | Annotated tree of the whole workspace or a subset |
| `show` | Card for the current epic/story (cwd-inferred) |
| `cd KEY` | Jump to an epic or story directory by Jira key |
| `cd ..` | Up one level (refuses to leave `.jira/`) |

### View

| Command | What it does |
|---|---|
| `epic list` / `epic show KEY` | Table of epics / card for one |
| `story list [--epic KEY]` / `story show KEY` | Same for stories |
| `task list [KEY]` | Subtask table |
| `comment list [KEY]` / `comment last [KEY]` | All comments / most recent |

### Edit

| Command | What it does |
|---|---|
| `epic set [KEY] --status --priority --summary --owner --label --description` | Update epic fields |
| `story set [KEY] --status --priority --summary --assignee --label --description --epic --points` | Update story fields |
| `set` (cwd-inferred) | Routes to `epic set` or `story set` based on where you are |
| `start` / `done` / `block "reason"` | Story status shortcuts (cwd-inferred) |
| `edit` | `$EDITOR` on the current epic/story description |
| `task add "title"` / `task done N` / `task undone N` / `task edit N "title"` / `task delete N` | Subtask ops (ID is 1-indexed per story) |
| `comment add "..."` (or no arg for `$EDITOR`) | Append a comment |

### Create

| Command | What it does |
|---|---|
| `epic create "Summary" [--priority --owner --label --description]` | New epic with placeholder key `NEW-N` |
| `story create "Summary" [--epic --priority --assignee --label --description --points]` | New story, auto-links to epic if cwd is inside one |
| `task add "title"` | New subtask under the current story |

### Delete

| Command | What it does |
|---|---|
| `epic delete [KEY]` | Soft-mark the epic and cascade to child stories. Unpushed (`NEW-N`) items are removed immediately. |
| `story delete [KEY]` | Soft-mark a single story |
| `task delete N` | Remove immediately (sub-task issue deleted on `merge`) |
| `epic undelete [KEY]` / `story undelete [KEY]` | Clear the deletion mark (epic-undelete cascades) |

### Sync

| Command | What it does |
|---|---|
| `pm clone [--force]` | Mirror the configured board into `.jira/` |
| `pm status` | Grouped table of every dirty file |
| `pm diff [KEY]` | Unified diff; in the TUI, `diff` (no args) opens a modal viewer |
| `pm merge [--yes] [--dry-run]` | Push local changes to Jira. Yes/No modal first (or `typer.confirm` in one-shot) |

---

## Workspace layout

```
.jira/
  config.json                  # baseUrl, email, apiToken, boardId, statusMap, projectKey, ...
  epics/
    <KEY>_<slug>/
      epic.json
      <STORY_KEY>_<slug>/
        story.json
        tasks.json             # [{id, key, title, done, status, _unpushed?}]
        comments.json          # [{id, author, body (ADF), _unpushed?}]
  unparented/                   # stories without an epic (rare)
  .baseline/<KEY>.json          # raw Jira payloads from last clone — diffed against current state
  .log/push-<ts>.json           # merge history
```

**Conventions:**

- Item directory names are `<JIRA_KEY>_<slug>` — slug is a lowercased, ASCII-folded summary.
- `_unpushed: true` marks records you've created locally that don't exist in Jira yet.
- `_deleted: true` marks records pending Jira deletion on next `merge`.
- All JSON writes are atomic (tmp + fsync + rename).

---

## Architecture

```
src/pm_shell/
  cli.py            typer entry — `pm` (no args) opens the TUI
  io.py             shared rich Console (force_terminal=True so TUI can capture ANSI)
  config.py         Config pydantic model; load/save .jira/config.json
  jira/client.py    JiraClient (httpx, basic auth) — search, get_issue, transitions, ...
  commands/         typer commands; thin layer over the engine
  sync/
    clone.py        clone() — initial board mirror
    shape.py        raw Jira payload → workspace shape (shared by clone + diff)
    diff.py         Change records + unified-diff renderer
    push.py         merge() — applies changes via Jira REST in dependency order
  render/           rich tables and cards (visual layer)
  workspace/        on-disk helpers (paths, atomic writes, tree walk)
  tui/
    app.py          PMShell — chat-style Textual app
    diff_screen.py  modal: file list + diff pane
    confirm_screen.py  Yes/No modal for merge
  shell/            legacy prompt_toolkit REPL (still available via `pm shell --simple`)
```

Skill ships from `skills/pm-shell/SKILL.md`.

---

## Known limits

These are documented limits, not bugs. Each has a planned solution but isn't built yet.

- **No conflict detection on `merge`** — last-write-wins. Safe for solo workspaces; collaborative use needs a re-fetch-before-write pass.
- **Sub-task modifications / deletions** are not pushed by `merge` — only new sub-tasks are created. Re-titling or status-changing an existing sub-task locally won't sync.
- **Assignee email → accountId** uses Jira's `/user/search`. No match means the field is sent as `null` with a warning in the merge outcome.
- **Story points** field ID is auto-detected per merge (looks for the field named "Story Points" or "Story point estimate"). `pm create` provisions this field tenant-wide on first use, so spaces created through the CLI always have it. For workspaces pointed at boards you didn't create (the "Alternative" setup path), if the project has no points field the value is skipped with a single warning rather than failing the push.
- **Issue-type names** (`Story` / `Task` / `User Story` / etc) are project-specific. The bundled spec creates a project that has `Story`, which is what the CLI's local records use. Pointing pm-shell at an arbitrary existing project that lacks an issue type literally called `Story` is the main rough edge today.
- **Cloned-priority round-trip**: the workspace stores priority as the lowercased Jira name (e.g. `"highest"`), but the CLI's canonical set is `low/medium/high/critical`. A story originally cloned with priority `Highest` can't currently be edited through the CLI and pushed back — `merge` will skip the field with a warning.
- **`pm pull` (incremental refresh)** isn't implemented yet. To re-sync, run `pm clone --force` (which wipes any unpushed local edits).

---

## Contributing

```bash
git clone <this-repo>
cd pm-shell
uv sync
uv run pytest         # if tests are present
uv run pm --version   # smoke test
```

For local development, install in editable mode (`uv tool install --editable .`) so the global `pm` reflects your source changes.

Reading order for new contributors:

1. This README
2. `src/pm_shell/cli.py` — wires every command together
3. `src/pm_shell/commands/` — one module per noun (epic, story, task, comment, sync)
4. `src/pm_shell/sync/{shape,diff,push}.py` — the engine for clone/status/diff/merge
5. `src/pm_shell/tui/app.py` — the interactive shell

---

## License

See [LICENSE](LICENSE).
