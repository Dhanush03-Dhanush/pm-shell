# Claude Code skills — pm-shell

Two skills that teach Claude Code how to drive the `pm` CLI for any repo with a `.jira/` directory. They're split by intent so Claude loads only the one relevant to the current task:

| Skill | When it activates |
|---|---|
| [`pm-refine`](pm-refine/SKILL.md) | Planning — creating epics, stories, tasks; breaking down features; scaffolding a backlog |
| [`pm-work`](pm-work/SKILL.md) | Implementation — updating status as work progresses, logging decisions/gotchas to comments, closing stories |

Each skill detects its trigger from the user's wording (e.g. *"let's plan auth"* → `pm-refine`, *"implement KAN-5"* → `pm-work`) and from whether `.jira/` exists in or above the current directory.

## Install (global — all repos)

```bash
mkdir -p ~/.claude/skills/pm-refine ~/.claude/skills/pm-work
cp skills/pm-refine/SKILL.md  ~/.claude/skills/pm-refine/SKILL.md
cp skills/pm-work/SKILL.md    ~/.claude/skills/pm-work/SKILL.md
```

Claude picks them up on the next session.

## Install (per-project)

Drop them inside the target repo instead of `~/.claude/`:

```bash
mkdir -p .claude/skills/pm-refine .claude/skills/pm-work
cp /path/to/pm-shell/skills/pm-refine/SKILL.md .claude/skills/pm-refine/SKILL.md
cp /path/to/pm-shell/skills/pm-work/SKILL.md   .claude/skills/pm-work/SKILL.md
```

## What they do (in one line each)

- **`pm-refine`** — asks 1–2 clarifying questions for vague requests, scaffolds epics/stories/tasks following INVEST and a title style guide, never invents acceptance criteria, never auto-estimates story points.
- **`pm-work`** — reads story + tasks + comments before coding, marks tasks done as it works, logs important context to comments using a `[decision]` / `[constraint]` / `[gotcha]` / `[deferred]` / `[ref]` taxonomy, summarizes before any `pm merge`.

Both skills **never run `pm merge` unprompted** — push to Jira always requires explicit user approval.

## Structure of each `SKILL.md`

Each skill is split into two clearly-delimited sections:

1. **Core (locked)** — How the LLM interacts with `pm`: workspace check, the `pm --help` discovery rule, and non-negotiable safety rules (no direct `.jira/*.json` edits, no unprompted `pm merge`). **Do not edit this section** — it's what keeps the LLM from breaking your local workspace.
2. **Team preferences (editable)** — Your team's planning and implementation conventions: title style, INVEST rules, story-points policy, comment taxonomy, work-loop steps. **Edit this section freely** to match how your team works.

The two sections are separated by an `<!-- === ... === -->` band and a clear header notice, so it's obvious which part you're touching when editing raw markdown.

Rule of thumb: if your change is about **what makes a good story / comment / title**, edit Team preferences. If your change is about **what commands the LLM runs or what files it touches**, you almost certainly don't need to edit anything — Core handles that via `pm --help` discovery.
