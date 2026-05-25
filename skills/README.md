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
