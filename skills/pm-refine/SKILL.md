---
name: pm-refine
description: Use when the user wants to plan, scope, or refine work — creating epics, stories, or tasks; breaking down a feature; scaffolding a backlog. Triggers include "refine", "plan", "scope", "break down", "groom the backlog", "create epic/story", "let's plan X", "spin up a story", "what stories do we need". Requires a `.jira/` workspace at the repo root or a parent dir; if absent, suggest `pm clone` first. For implementing an already-scaffolded story, use the `pm-work` skill instead.
---

# pm-refine

Use this skill to help the user **plan work** — scaffolding epics, stories, and tasks in the local `.jira/` mirror through the `pm` CLI. All edits stay local until the user runs `pm merge`.

This skill is for *creating structure*. For implementing an existing story, use `pm-work`.

## Workspace check

```bash
test -d .jira/ && which pm        # both should succeed
pm tree                            # what already exists
```

If `pm` isn't on PATH it lives at `~/.local/bin/pm` — tell the user; don't try to install it yourself.

## The refinement loop

1. **Listen** to what the user wants.
2. **Clarify** if the request is vague (see next section).
3. **Scaffold** epics/stories/tasks via `pm` commands.
4. **Review** with `pm tree` — show the user what was built.
5. **Adjust** based on feedback (rename, re-parent, delete).
6. **Stop** — never run `pm merge` unprompted.

## Clarify before scaffolding

For any vague request ("we should improve auth", "let's plan the next sprint"), **ask 1–2 clarifying questions first**. Don't invent a 7-story epic from one sentence.

Useful questions, by category:

- **Scope** — "What's in and out? Just the OAuth handler, or also session refresh and metrics?"
- **Success** — "What does 'done' look like? User-facing change, internal API, both?"
- **Priority** — "Must-have for the next release, or backlog candidate?"
- **Shape** — "One epic with several stories, or several smaller epics?"

Ask the minimum needed. If the user is specific ("create an epic X with stories A, B, C"), skip the questions and scaffold.

## Title style guide

| Item | Format | Good | Bad |
|---|---|---|---|
| Epic | Outcome-oriented noun phrase | "Authentication overhaul", "Mobile onboarding" | "Auth stuff", "Misc cleanup" |
| Story | Action-oriented, user-facing when possible | "Add SSO via Okta", "Cache user permissions on first request" | "OAuth", "Permission work" |
| Task | Imperative verb + concrete noun | "Wire OAuth callback handler", "Add unit tests for token refresh" | "OAuth callback", "Tests" |

Specifics over abstractions. "Add SSO via Okta" tells a future reader something; "Auth stuff" doesn't.

## Creating epics

```bash
pm epic create "Authentication overhaul" --priority high --label auth --description "..."
# → NEW-1 placeholder
```

An epic should:

- Take **weeks**, not days. If it fits in one PR, it's a story, not an epic.
- Have a clear business or technical outcome.
- Decompose into roughly 3–15 stories. More → split into multiple epics.

If the user gives context but no explicit description, summarize what you've heard into a `--description` capturing the *why*, the scope, and what success looks like. Always show the result and ask "does this capture it?"

## Creating stories

```bash
pm story create "Add SSO via Okta" --epic NEW-1 --priority high
# → NEW-2 under NEW-1

# Inside an epic dir, --epic is inferred from cwd:
cd NEW-1
pm story create "Session refresh flow"
```

A good story passes the **INVEST** check:

- **Independent** — implementable without blocking on another story
- **Valuable** — delivers a vertical slice (not just "backend half")
- **Estimable** — small enough to size
- **Small** — fits in ~1–5 days
- **Testable** — there's a clear "done" condition

If a story obviously needs 8+ subtasks, suggest splitting it. If you can't describe "done" in one sentence, it's too big or too vague.

## Acceptance criteria — never invent

Stories need acceptance criteria so the implementer knows when it's complete. **If the user hasn't given you the criteria, ask — don't make them up.** Hallucinated criteria create false confidence and misdirect future work.

When the user provides them, capture via:

```bash
pm story set NEW-2 --description "Acceptance criteria:
- User can click 'Sign in with Okta' and complete the OAuth flow.
- Failed auth shows a clear error message.
- Session persists across browser restarts for 24h."
```

Or `pm story edit NEW-2` to open `$EDITOR` (only when the user is in an interactive shell).

## Story points

**Leave points blank unless the user asks.** Story points are team-relative — what's a "3" for one team is a "5" for another. An LLM guessing them adds noise to the backlog.

When the user does ask, recommend Fibonacci: 1, 2, 3, 5, 8. Anything ≥13 should be split into smaller stories.

```bash
pm story set NEW-2 --points 5
```

## Creating tasks (subtasks under a story)

```bash
cd NEW-2
pm task add "Wire OAuth callback handler"
pm task add "Add session persistence layer"
pm task add "Write integration tests for happy path"
```

Tasks are the *technical breakdown* — written for the implementer (often the same LLM that just refined them). They should:

- Use imperative verbs ("Wire X", "Add Y", "Refactor Z").
- Have a single clear completion criterion.
- Be hours of work, not minutes or days.

Rule of thumb: a story with 3–7 tasks is healthy. Fewer than 3 means tasks are too coarse; more than 7 usually means the story is too big.

## Review with the user

After scaffolding, always show what was built:

```bash
pm tree                # full workspace
pm tree NEW-1          # just the new epic
```

Then ask explicitly: "Here's what I scaffolded. Want me to adjust anything, add more tasks, or move on?" Catching missing context now is cheaper than fixing structure later.

## What NOT to do

- **Don't run `pm merge`.** Refinement stays local until the user explicitly approves push.
- **Don't invent acceptance criteria** the user hasn't given you.
- **Don't auto-assign story points** unless asked.
- **Don't over-decompose.** Three thoughtful tasks beat ten generic ones.
- **Don't create epics for one-off work.** A standalone bug fix is a story or a task, not its own epic.
- **Don't edit `.jira/*.json` files directly.** Use `pm` so `_unpushed` flags and key mappings stay correct.

## Handoff to implementation

When refinement is done and the user wants to start implementing one of the new stories, this skill is done. The `pm-work` skill takes over for the build phase.
