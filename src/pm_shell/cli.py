from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console

from pm_shell import __version__
from pm_shell.config import (
    ConfigNotFoundError,
    config_path,
    load_config,
    save_config,
    secrets_to_config,
)
from pm_shell.commands import comment as comment_cmd
from pm_shell.commands import epic as epic_cmd
from pm_shell.commands import nav
from pm_shell.commands import story as story_cmd
from pm_shell.commands import task as task_cmd
from pm_shell.jira.client import JiraClient, JiraHTTPError
from pm_shell.sync.clone import DirtyWorkspaceError, clone

app = typer.Typer(
    name="pm",
    help="A git-like shell for Jira boards. Clone once, edit locally, push when ready.",
    no_args_is_help=True,
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
app.command("start", help="Shorthand for `story start` (cwd-inferred).")(story_cmd.story_start)
app.command("done", help="Shorthand for `story done` (cwd-inferred).")(story_cmd.story_done)
app.command("block", help="Shorthand for `story block` (cwd-inferred).")(story_cmd.story_block)
app.command("set", help="Shorthand for `story set` (cwd-inferred).")(story_cmd.story_set)


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

console = Console()
err_console = Console(stderr=True)


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"pm-shell {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        Optional[bool],
        typer.Option("--version", callback=_version_callback, is_eager=True, help="Show version and exit."),
    ] = None,
) -> None:
    """pm — interact with a local Jira mirror."""


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
    force: Annotated[
        bool,
        typer.Option("--force", help="Wipe and re-clone even if a local tree exists."),
    ] = False,
) -> None:
    """Clone the configured Jira board into .jira/."""
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
