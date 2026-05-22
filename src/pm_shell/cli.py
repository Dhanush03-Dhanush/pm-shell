from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated, Optional

import typer

from pm_shell import __version__
from pm_shell.commands import comment as comment_cmd
from pm_shell.commands import epic as epic_cmd
from pm_shell.commands import nav
from pm_shell.commands import story as story_cmd
from pm_shell.commands import sync as sync_cmd
from pm_shell.commands import task as task_cmd
from pm_shell.config import (
    Config,
    ConfigNotFoundError,
    config_path,
    load_config,
    save_config,
    secrets_to_config,
)
from pm_shell.global_store import (
    GlobalConfigError,
    global_dir,
    load_secrets,
    load_spaces,
    register_space,
    resolve_space,
    spaces_path,
)
from pm_shell.io import console, err_console
from pm_shell.jira.client import JiraClient, JiraHTTPError
from pm_shell.sync.clone import DirtyWorkspaceError, clone

_PROJECT_KEY_RE = re.compile(r"^[A-Z][A-Z0-9]{1,9}$")
_SCRUM_TEMPLATE = "com.pyxis.greenhopper.jira:gh-simplified-agility-scrum"

app = typer.Typer(
    name="pm",
    help="A git-like shell for Jira boards. Clone once, edit locally, push when ready.",
    add_completion=False,
)
config_app = typer.Typer(help="Manage local pm-shell configuration.", no_args_is_help=True)
app.add_typer(config_app, name="config")
app.add_typer(epic_cmd.app, name="epic")
app.add_typer(story_cmd.app, name="story")
app.add_typer(task_cmd.app, name="task")
app.add_typer(comment_cmd.app, name="comment")
app.command("ls")(nav.ls)
app.command("tree")(nav.tree)
app.command("show")(nav.show)
app.command("status", help="Show all locally modified, added, or deleted items.")(sync_cmd.status)
app.command("diff", help="Print unified diffs for changed files.")(sync_cmd.diff)
app.command("merge", help="Push local changes to Jira (confirmation prompt).")(sync_cmd.merge)
app.command("start", help="Shorthand for `story start` (cwd-inferred).")(story_cmd.story_start)
app.command("done", help="Shorthand for `story done` (cwd-inferred).")(story_cmd.story_done)
app.command("block", help="Shorthand for `story block` (cwd-inferred).")(story_cmd.story_block)


@app.command("set")
def smart_set(
    status: Annotated[Optional[str], typer.Option("--status", help="todo | in-progress | done | blocked.")] = None,
    priority: Annotated[Optional[str], typer.Option("--priority", help="low | medium | high | critical.")] = None,
    summary: Annotated[Optional[str], typer.Option("--summary", help="New title.")] = None,
    label: Annotated[Optional[list[str]], typer.Option("--label", help="Add a label. Repeatable.")] = None,
    description: Annotated[Optional[str], typer.Option("--description", help="Inline description.")] = None,
    owner: Annotated[Optional[str], typer.Option("--owner", help="Epic owner email. Pass '' to clear.")] = None,
    assignee: Annotated[Optional[str], typer.Option("--assignee", help="Story assignee email. Pass '' to clear.")] = None,
    epic: Annotated[Optional[str], typer.Option("--epic", help="Reparent story to a different epic.")] = None,
    points: Annotated[Optional[int], typer.Option("--points", help="Story points (integer).")] = None,
) -> None:
    """Update fields on the current epic or story (cwd-inferred).

    Routes to `epic set` when cwd is inside an epic dir (no story), to `story set`
    when inside a story dir. Flags that don't apply to the current item type are
    ignored with a warning so the same muscle memory works for both.
    """
    from pm_shell.workspace.paths import resolve_context

    epic_key, story_key = resolve_context()
    if story_key:
        if owner is not None:
            err_console.print("[dim]--owner is epic-only; ignored on a story[/]")
        story_cmd.story_set(
            key=story_key,
            status=status, priority=priority, summary=summary,
            assignee=assignee, label=label, description=description,
            epic=epic, points=points,
        )
        return

    if epic_key:
        story_only = {"--assignee": assignee, "--epic": epic, "--points": points}
        ignored = [name for name, val in story_only.items() if val is not None]
        if ignored:
            err_console.print(f"[dim]{', '.join(ignored)} are story-only; ignored on an epic[/]")
        epic_cmd.epic_set(
            key=epic_key,
            status=status, priority=priority, summary=summary,
            owner=owner, label=label, description=description,
        )
        return

    err_console.print(
        "[yellow]No context.[/] cd into an epic or story directory, "
        "or use `pm epic set KEY ...` / `pm story set KEY ...` explicitly."
    )
    raise typer.Exit(code=1)


@app.command("edit")
def smart_edit() -> None:
    """Open description in $EDITOR — story or epic depending on cwd."""
    from pm_shell.workspace.paths import resolve_context
    epic_key, story_key = resolve_context()
    if story_key:
        story_cmd.story_edit(story_key)
        return
    if epic_key:
        epic_cmd.epic_edit(epic_key)
        return
    err_console.print(
        "[yellow]No context.[/] Run from inside an epic or story directory, "
        "or use `pm epic edit KEY` / `pm story edit KEY`."
    )
    raise typer.Exit(code=1)


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"pm-shell {__version__}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: Annotated[
        Optional[bool],
        typer.Option("--version", callback=_version_callback, is_eager=True, help="Show version and exit."),
    ] = None,
) -> None:
    """pm — interact with a local Jira mirror. With no subcommand, opens the Textual shell."""
    if ctx.invoked_subcommand is None:
        _launch_shell()


@app.command("shell", help="Open the interactive pm-shell (Textual TUI).")
def cmd_shell(
    simple: Annotated[
        bool,
        typer.Option("--simple", help="Use the lightweight prompt_toolkit REPL instead of the TUI."),
    ] = False,
) -> None:
    _launch_shell(simple=simple)


def _launch_shell(*, simple: bool = False) -> None:
    """Open either the Textual TUI (default) or the prompt_toolkit REPL (--simple / non-TTY)."""
    import sys

    use_tui = not simple and sys.stdin.isatty() and sys.stdout.isatty()
    if use_tui:
        from pm_shell.tui import run_tui
        raise typer.Exit(code=run_tui(app))
    from pm_shell.shell.repl import run_repl
    raise typer.Exit(code=run_repl(app))


@config_app.command("init")
def config_init(
    from_file: Annotated[
        Optional[Path],
        typer.Option("--from", "-f", help="Path to a JSON file containing baseUrl, email, apiToken, boardId."),
    ] = None,
    force: Annotated[
        bool,
        typer.Option("--force", help="Overwrite an existing .jira/config.json."),
    ] = False,
) -> None:
    """Initialize .jira/config.json from a secrets file."""
    target = config_path()
    if target.exists() and not force:
        err_console.print(f"[yellow]config already exists at {target}[/]. Use --force to overwrite.")
        raise typer.Exit(code=1)

    if from_file is None:
        err_console.print("[red]Interactive prompts not implemented yet.[/] Pass --from <secrets.json>.")
        raise typer.Exit(code=2)

    if not from_file.exists():
        err_console.print(f"[red]Secrets file not found:[/] {from_file}")
        raise typer.Exit(code=2)

    cfg = secrets_to_config(from_file)
    save_config(cfg)
    console.print(f"[green]Wrote[/] {target} (chmod 600)")


@app.command("clone")
def cmd_clone(
    space: Annotated[
        Optional[str],
        typer.Option("--space", help="Bootstrap .jira/config.json from a space registered via `pm create`."),
    ] = None,
    force: Annotated[
        bool,
        typer.Option("--force", help="Wipe and re-clone even if a local tree exists."),
    ] = False,
) -> None:
    """Clone the configured Jira board into .jira/.

    With `--space NAME`, looks up the boardId in ~/.config/pm-shell/spaces.json,
    writes .jira/config.json in the current directory, then clones. Pair with
    `pm create` to bootstrap brand-new workspaces by name.
    """
    if space is not None:
        _bootstrap_workspace_from_space(space, force=force)

    try:
        cfg = load_config()
    except ConfigNotFoundError as exc:
        err_console.print(f"[red]{exc}[/]")
        raise typer.Exit(code=1) from None

    try:
        summary = clone(cfg, force=force, progress=lambda msg: console.print(f"[dim]{msg}[/]"))
    except DirtyWorkspaceError as exc:
        err_console.print(f"[yellow]{exc}[/]")
        raise typer.Exit(code=1) from None
    except JiraHTTPError as exc:
        err_console.print(f"[red]Jira error:[/] {exc}")
        raise typer.Exit(code=1) from None

    console.print()
    console.print("[green]Clone complete.[/]")
    console.print(
        f"  epics:    {summary['epics']}\n"
        f"  stories:  {summary['stories']}\n"
        f"  tasks:    {summary['tasks']}\n"
        f"  comments: {summary['comments']}"
    )


_POINTS_FIELD_NAMES = {"story points", "story point estimate"}
_POINTS_FIELD_SPEC = {
    "name": "Story Points",
    "description": "Estimate of work for an issue (sprint planning).",
    "type": "com.atlassian.jira.plugin.system.customfieldtypes:float",
    "searcherKey": "com.atlassian.jira.plugin.system.customfieldtypes:exactnumber",
}


def _ensure_story_points_field(client: JiraClient) -> tuple[str, bool]:
    """Make sure the tenant has a Story Points number custom field.

    Returns `(field_id, created)`. Idempotent — re-running on a tenant that already
    has the field is a single GET. The field is tenant-wide, so creating it once
    means every team-managed project (existing and future) can use it.
    """
    fields = client.get("/rest/api/3/field") or []
    for f in fields:
        if (f.get("name") or "").lower() in _POINTS_FIELD_NAMES:
            return f["id"], False

    try:
        result = client.post("/rest/api/3/field", json=_POINTS_FIELD_SPEC)
    except JiraHTTPError as exc:
        if exc.status_code in (401, 403):
            err_console.print(
                f"[red]Cannot create the Story Points field:[/] {exc.status_code} {exc.body}\n"
                "Creating tenant-wide custom fields needs Jira-admin permission. "
                "Either grant your account that permission, or create the field by hand in "
                "Jira → Settings → Issues → Custom fields → Add (Number, name it 'Story Points')."
            )
            raise typer.Exit(code=2) from None
        err_console.print(
            f"[red]Failed to create Story Points field:[/] {exc.status_code} {exc.body}"
        )
        raise typer.Exit(code=1) from None
    return result["id"], True


def _bootstrap_workspace_from_space(space_name: str, *, force: bool) -> None:
    """Write `.jira/config.json` in cwd from the global secrets + named space.

    Refuses to overwrite an existing config unless `force=True`. The clone phase
    that runs after this call relies on the freshly-written config.
    """
    try:
        secrets = load_secrets()
        entry = resolve_space(space_name)
    except GlobalConfigError as exc:
        err_console.print(f"[red]{exc}[/]")
        raise typer.Exit(code=2) from None

    target = config_path()
    if target.exists() and not force:
        err_console.print(
            f"[yellow]Workspace already initialized at {target}.[/] "
            f"Re-run with --force to overwrite from space {space_name!r}."
        )
        raise typer.Exit(code=1)

    cfg = Config.model_validate({
        **secrets,
        "boardId": entry["boardId"],
        "projectKey": entry["projectKey"],
    })
    save_config(cfg)
    console.print(f"[dim]wrote {target} from space {space_name!r}[/]")


@app.command("create")
def cmd_create(
    name: Annotated[
        Optional[str],
        typer.Option("--name", help="Display name for the space (prompted if omitted)."),
    ] = None,
    key: Annotated[
        Optional[str],
        typer.Option("--key", help="2–10 char uppercase Jira project key (prompted if omitted)."),
    ] = None,
    description: Annotated[
        Optional[str],
        typer.Option("--description", help="Project description (optional)."),
    ] = None,
) -> None:
    """Create a new Jira project (a "space") and register it for `pm clone --space`.

    Requires ~/.config/pm-shell/secrets.json with baseUrl, email, apiToken.
    Hard-coded to the team-managed Scrum template — that gives you Epic / Story /
    Task / Subtask issue types and the standard Highest..Lowest priorities.

    Also guarantees the tenant has a Story Points number custom field (creates one
    the first time, idempotent thereafter). Together that's the configuration
    `pm merge` is built around — no follow-up Jira-UI work needed for points to
    round-trip on stories created in the new space.
    """
    try:
        secrets = load_secrets()
    except GlobalConfigError as exc:
        err_console.print(f"[red]{exc}[/]")
        raise typer.Exit(code=2) from None

    if name is None:
        name = typer.prompt("Space name").strip()
    if not name:
        err_console.print("[red]Space name cannot be empty.[/]")
        raise typer.Exit(code=2)

    if key is None:
        key = typer.prompt("Project key (2–10 uppercase letters/digits)").strip()
    key = key.upper()
    if not _PROJECT_KEY_RE.match(key):
        err_console.print(
            f"[red]Invalid project key {key!r}[/]: must start with a letter, "
            "2–10 uppercase letters/digits."
        )
        raise typer.Exit(code=2)

    existing = load_spaces()
    if name in existing:
        err_console.print(
            f"[red]Space {name!r} is already registered[/] "
            f"(key={existing[name].get('projectKey')}, boardId={existing[name].get('boardId')}). "
            f"Pick a different name."
        )
        raise typer.Exit(code=1)

    cfg = Config.model_validate(secrets)
    with JiraClient(cfg) as client:
        points_field_id, points_created = _ensure_story_points_field(client)
        if points_created:
            console.print(
                f"[green]Created tenant-wide Story Points field[/] "
                f"(id=[cyan]{points_field_id}[/]) — available to every team-managed project."
            )
        else:
            console.print(f"[dim]Story Points field already exists ({points_field_id}); reusing.[/]")

        lead = client.myself()["accountId"]
        body = {
            "key": key,
            "name": name,
            "projectTypeKey": "software",
            "projectTemplateKey": _SCRUM_TEMPLATE,
            "leadAccountId": lead,
            "assigneeType": "UNASSIGNED",
        }
        if description:
            body["description"] = description

        try:
            project = client.post("/rest/api/3/project", json=body)
        except JiraHTTPError as exc:
            err_console.print(f"[red]Jira refused project creation:[/] {exc.status_code} {exc.body}")
            raise typer.Exit(code=1) from None

        boards = client.get(
            "/rest/agile/1.0/board", params={"projectKeyOrId": project["key"]}
        ).get("values") or []
        board_id = boards[0]["id"] if boards else None

    if board_id is None:
        err_console.print(
            f"[yellow]Project {project['key']} created but no board was auto-provisioned.[/] "
            "Create one in the Jira UI, then add the entry to ~/.config/pm-shell/spaces.json by hand."
        )
        raise typer.Exit(code=1)

    register_space(name, project_key=project["key"], board_id=board_id)
    console.print()
    console.print(
        f"[green]Created space[/] [bold]{name}[/] "
        f"(key=[cyan]{project['key']}[/], boardId=[cyan]{board_id}[/])"
    )
    console.print(f"[dim]registered in {spaces_path()}[/]")
    console.print()
    console.print("Next:")
    console.print(f"  cd ~/some/workspace")
    console.print(f"  pm clone --space {name!r}")


@app.command("spaces")
def cmd_spaces() -> None:
    """List the Jira spaces registered for this machine."""
    try:
        spaces = load_spaces()
    except GlobalConfigError as exc:
        err_console.print(f"[red]{exc}[/]")
        raise typer.Exit(code=1) from None

    if not spaces:
        console.print(
            f"[dim]No spaces registered yet.[/] "
            f"Run [bold]pm create[/] to make one (registry: {spaces_path()})."
        )
        return

    from rich.table import Table
    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 1))
    table.add_column("NAME", no_wrap=True)
    table.add_column("KEY", no_wrap=True, style="cyan")
    table.add_column("BOARD ID", no_wrap=True, style="cyan")
    table.add_column("CREATED", style="dim")
    for name in sorted(spaces):
        entry = spaces[name]
        table.add_row(
            name,
            str(entry.get("projectKey", "?")),
            str(entry.get("boardId", "?")),
            (entry.get("createdAt", "") or "")[:19],
        )
    console.print(table)
    console.print(f"[dim]source: {spaces_path()}[/]")


@app.command("whoami")
def whoami() -> None:
    """Verify credentials by calling Jira /myself."""
    try:
        cfg = load_config()
    except ConfigNotFoundError as exc:
        err_console.print(f"[red]{exc}[/]")
        raise typer.Exit(code=1) from None

    with JiraClient(cfg) as client:
        try:
            me = client.myself()
        except JiraHTTPError as exc:
            err_console.print(f"[red]Jira error:[/] {exc}")
            raise typer.Exit(code=1) from None

    console.print(f"[bold]{me.get('displayName', '?')}[/]  <{me.get('emailAddress', '?')}>")
    console.print(f"accountId: {me.get('accountId', '?')}")
    console.print(f"timeZone:  {me.get('timeZone', '?')}")
