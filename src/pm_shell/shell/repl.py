from __future__ import annotations

import os
import shlex
from pathlib import Path
from typing import TYPE_CHECKING

import click
from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import FormattedText
from rich.console import Console

from pm_shell import __version__
from pm_shell.config import ConfigNotFoundError, load_config, workspace_dir
from pm_shell.shell.completion import PMCompleter
from pm_shell.workspace.paths import resolve_context, resolve_workspace_target

if TYPE_CHECKING:
    import typer

console = Console()
err_console = Console(stderr=True)

_EXIT_WORDS = {"exit", "quit", ":q"}


def _prompt_fragments() -> FormattedText:
    epic_key, story_key = resolve_context()
    parts = [k for k in (epic_key, story_key) if k]
    label = "/".join(parts) if parts else "~"
    return FormattedText([("ansicyan bold", label), ("", " > ")])


def _builtin_cd(args: list[str]) -> None:
    if not args:
        target: Path = workspace_dir()
    else:
        arg = args[0]
        resolved = resolve_workspace_target(arg)
        if resolved is not None:
            target = resolved
        else:
            target = Path(arg).expanduser()
    try:
        os.chdir(target)
    except FileNotFoundError:
        err_console.print(f"[red]cd:[/] no such directory: {args[0] if args else target}")
    except NotADirectoryError:
        err_console.print(f"[red]cd:[/] not a directory: {target}")
    except PermissionError:
        err_console.print(f"[red]cd:[/] permission denied: {target}")


def _builtin_pwd() -> None:
    console.print(str(Path.cwd()))


def _builtin_clear() -> None:
    print("\033[2J\033[H", end="", flush=True)


def _print_help() -> None:
    console.print(
        "[bold]Shell built-ins[/]\n"
        "  cd [path]    change directory (no arg → workspace root)\n"
        "  pwd          print working directory\n"
        "  clear        clear the screen\n"
        "  exit | quit  leave the shell (or Ctrl-D)\n"
        "  help         this help\n"
        "\n"
        "[bold]Workspace commands[/] (append [dim]--help[/] for flags)\n"
        "  ls, tree, show         navigate / view\n"
        "  epic, story, task, comment\n"
        "  set, start, done, block, edit          (story shortcuts; cwd-aware)\n"
        "  clone, whoami, config\n"
        "\n"
        "[dim]The prompt shows your current context, e.g. KAN-4/KAN-5 > —[/]\n"
        "[dim]commands inside a story dir don't need the story key.[/]"
    )


def _banner() -> None:
    try:
        cfg = load_config()
    except ConfigNotFoundError:
        console.print(
            f"[bold]pm-shell {__version__}[/]  ·  [yellow]no workspace[/]\n"
            "[dim]Run `config init --from <secrets.json>` then `clone` to get started.[/]"
        )
        return

    project = "?"
    if cfg.base_url:
        try:
            project = cfg.base_url.split("//", 1)[-1].split(".", 1)[0]
        except (IndexError, AttributeError):
            pass

    epic_count = story_count = 0
    try:
        from pm_shell.workspace.tree import list_epics, list_stories
        epic_count = len(list_epics())
        story_count = len(list_stories())
    except Exception:
        pass

    console.print(
        f"[bold]pm-shell {__version__}[/]  ·  [cyan]{project}[/]  "
        f"·  {epic_count} epics, {story_count} stories"
    )
    console.print("[dim]type `help` for commands, `exit` to quit[/]")


def _dispatch(app: "typer.Typer", argv: list[str]) -> None:
    """Run a typer command without sys.exiting the REPL."""
    from typer.main import get_command

    cmd = get_command(app)
    try:
        cmd.main(args=argv, prog_name="pm", standalone_mode=False)
    except click.exceptions.UsageError as exc:
        exc.show()
    except click.exceptions.ClickException as exc:
        exc.show()
    except KeyboardInterrupt:
        err_console.print("[yellow]^C[/]")
    except SystemExit:
        # Some commands (e.g. --help) raise SystemExit even in standalone_mode=False.
        pass
    except Exception as exc:  # noqa: BLE001 — REPL must survive unexpected errors
        err_console.print(f"[red]error:[/] {exc!s}")


def run_repl(app: "typer.Typer") -> int:
    """Interactive shell over the existing typer app. Returns the desired process exit code."""
    completer = PMCompleter(app)
    session: PromptSession = PromptSession(
        completer=completer,
        complete_while_typing=False,
    )
    _banner()

    while True:
        try:
            line = session.prompt(_prompt_fragments)
        except KeyboardInterrupt:
            continue
        except EOFError:
            break

        line = line.strip()
        if not line:
            continue

        try:
            argv = shlex.split(line)
        except ValueError as exc:
            err_console.print(f"[red]parse error:[/] {exc}")
            continue

        head, rest = argv[0], argv[1:]

        if head in _EXIT_WORDS:
            break
        if head == "help":
            _print_help()
            continue
        if head == "cd":
            _builtin_cd(rest)
            continue
        if head == "pwd":
            _builtin_pwd()
            continue
        if head == "clear":
            _builtin_clear()
            continue

        _dispatch(app, argv)

        # Mutations may have added/removed keys (task add, etc.). Cheap to invalidate;
        # the next Tab press repopulates from disk.
        if head in ("clone", "task", "story", "epic", "comment"):
            completer.refresh_keys()

    console.print("[dim]bye[/]")
    return 0
