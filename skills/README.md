# Claude Code skill — pm-shell

A skill that teaches Claude Code when and how to drive the `pm` CLI for any repo with a `.jira/` directory.

## Installing

Copy the skill into your global Claude Code skills directory:

```bash
mkdir -p ~/.claude/skills/pm-shell
cp skills/pm-shell/SKILL.md ~/.claude/skills/pm-shell/SKILL.md
```

That's it — next time Claude Code starts, it'll pick the skill up automatically. Claude invokes it whenever a workspace contains `.jira/` or the user references Jira keys (`KAN-5`, `PROJ-12`, etc.).

## What it does

- Reads `.jira/epics/<EPIC>/<STORY>/story.json` for acceptance criteria and `tasks.json` for the subtask checklist.
- Marks tasks/stories done via `pm task done N` / `pm done` as work progresses.
- Adds working comments with `pm comment add "..."` to leave a trail.
- During refinement, scaffolds new epics/stories via `pm epic create` / `pm story create` based on user requirements.
- Surfaces local changes with `pm status` and `pm diff` before any push.
- **Never** runs `pm merge` unprompted — merge requires explicit user approval.

See `pm-shell/SKILL.md` for the full body Claude reads.

## Per-project install

If you only want this skill active in one repo (rather than globally), drop it at `<repo>/.claude/skills/pm-shell/SKILL.md` instead of `~/.claude/skills/`.
