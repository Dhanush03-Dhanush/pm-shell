from __future__ import annotations

import os
import shlex
from pathlib import Path
from typing import TYPE_CHECKING

import click
from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import FormattedText

from pm_shell import __version__
from pm_shell.branding import banner as _render_banner, project_from_url
from pm_shell.config import ConfigNotFoundError, load_config, workspace_dir
from pm_shell.io import console, err_console
from pm_shell.shell.completion import PMCompleter
from pm_shell.workspace.paths import resolve_context, resolve_workspace_target

if TYPE_CHECKING:
    import typer

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
        console.print(_render_banner(version=__version__))
        return

    epic_count = story_count = 0
    try:
        from pm_shell.workspace.tree import list_epics, list_stories
        epic_count = len(list_epics())
        story_count = len(list_stories())
    except Exception:
        pass

    console.print(_render_banner(
        version=__version__,
        project=project_from_url(cfg.base_url),
        epic_count=epic_count,
        story_count=story_count,
    ))


def _dispatch(app: "typer.Typer", argv: list[str]) -> None:
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
        # `--help` raises SystemExit even with standalone_mode=False.
        pass
    except Exception as exc:  # noqa: BLE001 — REPL must survive unexpected errors
        err_console.print(f"[red]error:[/] {exc!s}")


def run_repl(app: "typer.Typer") -> int:
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

        if head in ("clone", "task", "story", "epic", "comment"):
            completer.refresh_keys()

    console.print("[dim]bye[/]")
    return 0
