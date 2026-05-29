---
name: pm-refine
description: Plan and scaffold work in a `.jira/` workspace via the `pm` CLI — creating epics, stories, and tasks; breaking features into a backlog. Triggers: "refine", "plan", "scope", "break down", "groom the backlog", "create epic/story". For implementing an already-scaffolded story, use `pm-work` instead.
---

# pm-refine

Two sections below:

1. **Core (locked)** — How to interact with `pm`. **Do not edit.**
2. **Team preferences (editable)** — Title style, sizing rules, story-points policy. **Edit this** to match your team.

<!-- ============================================================ -->
<!-- ===================== CORE — DO NOT EDIT ==================== -->
<!-- ============================================================ -->

## Core (locked)

> **Notice to the LLM:** Do not edit this section. It defines how you interact with `pm`. To change team conventions (titles, sizing, points, etc.), edit the **Team preferences** section below.

`pm` ("pm shell") is a git-like CLI that mirrors a Jira board into a local `.jira/` directory. You read and edit tickets locally; nothing reaches Jira until the user runs `pm merge`. Most commands are **cwd-aware** — running them inside an epic or story dir infers the key.

### Rules you must not break

1. **Never run `pm merge` unprompted.** Every push to Jira requires explicit user approval — every time, not once-per-session.
2. **Never edit `.jira/*.json` directly.** Always go through `pm` so `_unpushed` flags and key mappings stay correct.
3. **Never touch `.jira/.baseline/` or `.jira/config.json`.** Managed by clone/pull; `config.json` holds credentials.
4. **`pm clone --force` wipes local edits.** Suggest it only when the user wants to discard local state entirely.

### Discover commands via `--help` — never assume

**Always learn the current CLI surface from `pm --help` and `pm <command> --help`.** Do not rely on commands memorized from prior sessions; the CLI evolves. If a command you expect doesn't appear in `--help`, it doesn't exist — ask the user rather than guessing flag names.

```bash
pm --help                 # top-level commands
pm story --help           # subcommands for a group
pm story create --help    # flags + usage
```

### Before doing anything

```bash
pm --help           # learn the CLI
test -d .jira/      # confirm workspace
pm tree             # see current state
```

If `pm` isn't on `PATH`, ask the user where it's installed (a common install path is `~/.local/bin/pm`, but don't assume) — don't try to install it yourself. If `.jira/` is missing, suggest `pm clone` and stop.

### Refinement loop

1. **Listen** to what the user wants.
2. **Clarify** if vague (see Team preferences for question categories).
3. **Scaffold** epics/stories/tasks via `pm` — exact commands via `pm --help`.
4. **Review** with `pm tree` and show the user.
5. **Adjust** based on feedback.
6. **Stop.** Never run `pm merge`.

<!-- ============================================================ -->
<!-- ============== TEAM PREFERENCES — EDIT BELOW ================ -->
<!-- ============================================================ -->

## Team preferences (editable)

> **Edit this section** to match your team's planning conventions. Core above defines how the LLM talks to `pm`; this defines what your team considers good.

### Clarify before scaffolding

For vague requests ("we should improve auth", "let's plan next sprint"), **ask 1–2 clarifying questions first**. Don't invent a 7-story epic from one sentence.

Useful categories:

- **Scope** — "What's in and out?"
- **Success** — "What does 'done' look like? User-facing change, internal API, both?"
- **Priority** — "Must-have for next release, or backlog candidate?"
- **Shape** — "One epic with several stories, or several smaller epics?"

If the user is specific ("epic X with stories A, B, C"), skip questions and scaffold.

### Titles

| Item  | Format                          | Example                       |
| ----- | ------------------------------- | ----------------------------- |
| Epic  | Outcome-oriented noun phrase    | "Authentication overhaul"     |
| Story | Action-oriented, user-facing    | "Add SSO via Okta"            |
| Task  | Imperative verb + concrete noun | "Wire OAuth callback handler" |

Specifics over abstractions — "Add SSO via Okta" tells a future reader something; "Auth stuff" doesn't.

### Sizing

- **Epic** — weeks, not days. Decomposes into 3–15 stories. If it fits in one PR, it's a story, not an epic.
- **Story** — passes **INVEST**: Independent, Valuable (vertical slice — not just "backend half"), Estimable, Small (~1–5 days), Testable (describe "done" in one sentence). 8+ subtasks → split.
- **Task** — hours of work. Imperative verb + single completion criterion. 3–7 per story is healthy.

### Acceptance criteria — never invent

Stories need acceptance criteria so the implementer knows when it's complete. **If the user hasn't given criteria, ask — don't make them up.** Hallucinated criteria create false confidence and misdirect future work.

If the user gave context but no explicit criteria, summarize what you heard, show it, and ask: "does this capture it?"

### Story points

**Leave points blank unless the user asks.** Points are team-relative — what's a "3" for one team is a "5" for another. An LLM guessing them adds noise to the backlog.

When the user asks: recommend **Fibonacci** (1, 2, 3, 5, 8). Anything ≥13 → split.

### Epic descriptions

If the user gives context but no explicit description, draft one capturing the *why*, the scope, and what success looks like. Show it and ask "does this capture it?" Don't write descriptions silently.

### Review with the user

After scaffolding, always show `pm tree` and ask explicitly: "Here's what I scaffolded. Want me to adjust anything, add more tasks, or move on?" Catching missing context now is cheaper than fixing structure later.

### What NOT to do

- **Don't invent acceptance criteria** the user hasn't given you.
- **Don't auto-assign story points** unless asked.
- **Don't over-decompose** — three thoughtful tasks beat ten generic ones.
- **Don't create epics for one-off work** — a standalone bug fix is a story or a task.
