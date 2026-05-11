"""Textual app — chat-style shell for pm-shell.

Layout (top → bottom): banner / scrolling output log / prompt row / footer.
Commands dispatch through the same typer engine the one-shot CLI uses; output
is captured via `rich.console.Console.capture()` and rendered into the log as
ANSI-decoded Text so colours survive.
"""

from __future__ import annotations

import difflib
import os
import shlex
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import click
from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.document import Document
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.suggester import Suggester
from textual.widgets import Footer, Input, RichLog, Static

from pm_shell import __version__
from pm_shell.config import ConfigNotFoundError, load_config, workspace_dir
from pm_shell.io import console, err_console
from pm_shell.shell.completion import PMCompleter
from pm_shell.workspace.paths import resolve_context, resolve_workspace_target

if TYPE_CHECKING:
    import typer

_EXIT_WORDS = {"exit", "quit", ":q"}


class PMInput(Input):
    """Input that accepts the ghost-text suggestion on Tab (in addition to →)."""

    BINDINGS = [
        Binding("tab", "cursor_right", show=False, priority=True),
    ]


class PMLog(RichLog):
    """RichLog that can't take focus — clicks fall through, prompt keeps it."""

    can_focus = False


class PMSuggester(Suggester):
    """Inline ghost-text suggester backed by the existing PMCompleter."""

    def __init__(self, typer_app: "typer.Typer") -> None:
        super().__init__(use_cache=False, case_sensitive=False)
        self._completer = PMCompleter(typer_app)

    def refresh(self) -> None:
        self._completer.refresh_keys()

    async def get_suggestion(self, value: str) -> Optional[str]:
        if not value:
            return None
        doc = Document(value, len(value))
        for completion in self._completer.get_completions(doc, CompleteEvent()):
            partial = -completion.start_position
            prefix = value[:-partial] if partial > 0 else value
            full = prefix + completion.text
            if full != value and full.lower().startswith(value.lower()):
                return full
            return None
        return None


class PMShell(App):
    CSS_PATH = "styles.tcss"
    TITLE = "pm-shell"

    BINDINGS = [
        Binding("ctrl+d", "quit", "quit", show=True),
        Binding("ctrl+l", "clear_log", "clear", show=True),
        Binding("pageup", "scroll_log_up", "scroll", show=True),
        Binding("pagedown", "scroll_log_down", "", show=False),
        # No priority — keep ↑/↓ history at the bottom of the chain so widgets
        # like ListView (in DiffScreen) handle them first.
        Binding("up", "history_back", "history", show=True),
        Binding("down", "history_forward", "", show=False),
    ]

    def __init__(self, typer_app: "typer.Typer") -> None:
        super().__init__()
        self._typer_app = typer_app
        self._suggester = PMSuggester(typer_app)
        self._history: list[str] = []
        self._history_idx: Optional[int] = None
        self._original_cwd: Optional[Path] = None
        self._known_commands = _collect_known_commands(typer_app)

    def compose(self) -> ComposeResult:
        yield Static(self._banner_text(), id="banner")
        yield PMLog(
            id="log",
            wrap=False,
            markup=False,
            highlight=False,
            auto_scroll=True,
        )
        with Horizontal(id="prompt-row"):
            yield Static(self._context_label(), id="prompt-context")
            yield PMInput(placeholder="type a command — try `help`", id="prompt", suggester=self._suggester)
        yield Footer()

    def on_mount(self) -> None:
        self._original_cwd = Path.cwd().resolve()
        ws = workspace_dir()
        if ws.exists() and ws.is_dir():
            try:
                os.chdir(ws)
            except OSError:
                pass

        log = self.query_one("#log", RichLog)
        try:
            cfg = load_config()
            project = _project_from_url(cfg.base_url)
            log.write(Text.from_markup(
                f"[bold]pm-shell {__version__}[/]  ·  [cyan]{project}[/]\n"
                f"[dim]type `help` for commands, Ctrl-D to exit[/]"
            ))
        except ConfigNotFoundError:
            log.write(Text.from_markup(
                f"[bold]pm-shell {__version__}[/]  ·  [yellow]no workspace[/]\n"
                "[dim]Run `config init --from <secrets.json>` then `clone` to get started.[/]"
            ))
        self.query_one("#prompt", Input).focus()
        self._refresh_context()

    def on_unmount(self) -> None:
        if self._original_cwd is not None:
            try:
                os.chdir(self._original_cwd)
            except OSError:
                pass

    def _banner_text(self) -> str:
        return ""  # banner is rendered into the log on_mount; the Static is reserved for future status info

    def _context_label(self) -> Text:
        epic_key, story_key = resolve_context()
        label = Text()
        if not epic_key and not story_key:
            label.append("~", style="dim")
        else:
            if epic_key:
                label.append(epic_key, style="cyan bold")
            if story_key:
                if epic_key:
                    label.append("/", style="dim")
                label.append(story_key, style="magenta bold")
        label.append(" ›", style="dim")
        return label

    def _refresh_context(self) -> None:
        self.query_one("#prompt-context", Static).update(self._context_label())

    def on_input_submitted(self, event: Input.Submitted) -> None:
        line = event.value.strip()
        event.input.value = ""
        if not line:
            return

        self._history.append(line)
        self._history_idx = None

        log = self.query_one("#log", RichLog)
        echo = self._context_label().copy()
        echo.append(" ")
        echo.append(line)
        log.write(echo)

        try:
            argv = shlex.split(line)
        except ValueError as exc:
            log.write(Text.from_markup(f"[red]parse error:[/] {exc}"))
            return

        head, rest = argv[0], argv[1:]

        if head in _EXIT_WORDS:
            self.exit()
            return
        if head == "help":
            log.write(_HELP_TEXT)
            return
        if head == "cd":
            self._builtin_cd(rest, log)
            self._refresh_context()
            self._suggester.refresh()
            return
        if head == "pwd":
            log.write(Text(str(Path.cwd())))
            return
        if head == "clear":
            log.clear()
            return
        if head == "diff" and not rest:
            self._open_diff_screen()
            return

        if head not in self._known_commands:
            hint = difflib.get_close_matches(head, self._known_commands, n=1)
            suffix = f"  [dim]did you mean[/] [italic]{hint[0]}[/]?" if hint else ""
            log.write(Text.from_markup(f"[red bold]! Command not found:[/] [red]{head}[/]{suffix}"))
            return

        self._dispatch(argv, log)

        if head in {"clone", "task", "story", "epic", "comment", "config"}:
            self._suggester.refresh()
        self._refresh_context()

    def _dispatch(self, argv: list[str], log: RichLog) -> None:
        from typer.main import get_command

        cmd = get_command(self._typer_app)
        with console.capture() as cap_out, err_console.capture() as cap_err:
            try:
                cmd.main(args=argv, prog_name="pm", standalone_mode=False)
            except (click.exceptions.UsageError, click.exceptions.ClickException) as exc:
                exc.show()
            except (KeyboardInterrupt, SystemExit):
                pass
            except Exception as exc:  # noqa: BLE001 — TUI must survive unexpected errors
                err_console.print(f"[red]error:[/] {exc!s}")

        out_text = cap_out.get()
        err_text = cap_err.get()
        if out_text:
            log.write(Text.from_ansi(out_text.rstrip("\n")))
        if err_text:
            log.write(Text.from_ansi(err_text.rstrip("\n")))

    def _builtin_cd(self, args: list[str], log: RichLog) -> None:
        if not args:
            target: Path = workspace_dir()
        else:
            resolved = resolve_workspace_target(args[0])
            target = resolved if resolved is not None else Path(args[0]).expanduser()

        try:
            target_abs = target.resolve()
        except OSError:
            log.write(Text.from_markup(f"[red]cd:[/] cannot resolve: {target}"))
            return

        ws = workspace_dir().resolve()
        try:
            target_abs.relative_to(ws)
        except ValueError:
            log.write(Text.from_markup("[red]cd:[/] already at workspace root"))
            return

        try:
            os.chdir(target_abs)
        except FileNotFoundError:
            log.write(Text.from_markup(f"[red]cd:[/] no such directory: {args[0] if args else target_abs}"))
        except NotADirectoryError:
            log.write(Text.from_markup(f"[red]cd:[/] not a directory: {target_abs}"))
        except PermissionError:
            log.write(Text.from_markup(f"[red]cd:[/] permission denied: {target_abs}"))

    def _open_diff_screen(self) -> None:
        from pm_shell.sync.diff import compute_changes
        from pm_shell.tui.diff_screen import DiffScreen

        changes = compute_changes()
        if not changes:
            self.query_one("#log", RichLog).write(
                Text.from_markup("[dim]workspace is clean — nothing to diff[/dim]")
            )
            return
        self.push_screen(DiffScreen(changes))

    # ── Actions ──────────────────────────────────────────────────────────────
    def action_clear_log(self) -> None:
        self.query_one("#log", RichLog).clear()

    def action_scroll_log_up(self) -> None:
        self.query_one("#log", RichLog).scroll_page_up(animate=False)

    def action_scroll_log_down(self) -> None:
        self.query_one("#log", RichLog).scroll_page_down(animate=False)

    def action_history_back(self) -> None:
        if not self._history:
            return
        prompt = self.query_one("#prompt", Input)
        if self._history_idx is None:
            self._history_idx = len(self._history) - 1
        elif self._history_idx > 0:
            self._history_idx -= 1
        prompt.value = self._history[self._history_idx]
        prompt.cursor_position = len(prompt.value)

    def action_history_forward(self) -> None:
        if self._history_idx is None:
            return
        prompt = self.query_one("#prompt", Input)
        if self._history_idx < len(self._history) - 1:
            self._history_idx += 1
            prompt.value = self._history[self._history_idx]
        else:
            self._history_idx = None
            prompt.value = ""
        prompt.cursor_position = len(prompt.value)


_HELP_TEXT = Text.from_markup("""\
[bold]BROWSE[/]
  [dim]ls[/]                              what's at the current location
  [dim]tree[/]                            the whole workspace tree
  [dim]tree KAN-4[/]                      tree scoped to one epic
  [dim]show[/]                            smart card for the current epic/story

[bold]NAVIGATE[/]   [italic dim]cd is key-aware — keys are unique IDs, no slug needed[/]
  [dim]cd KAN-4[/]                        into an epic
  [dim]cd KAN-5[/]                        into a story (works from anywhere)
  [dim]cd ..[/]                           up one level
  [dim]cd[/]                              back to workspace root

[bold]VIEW[/]
  [cyan]epic show KAN-4[/]                 epic card + story list
  [magenta]story show KAN-5[/]                story card + tasks + latest comment
  [green]task list KAN-5[/]                 task table (or [green]task list[/] inside a story dir)
  [yellow]comment list KAN-5[/]              all comments

[bold]EDIT[/]   [italic dim]all changes are local — push (Phase 6) syncs them to Jira[/]
  [magenta]story set KAN-5 --status in-progress --priority high[/]
  [magenta]set --status done[/]                inside a story dir, cwd-inferred
  [cyan]epic set KAN-4 --priority critical --label backend[/]
  [magenta]start[/] [dim]/[/] [magenta]done[/] [dim]/[/] [magenta]block "reason"[/]      shortcuts (in story dir)
  [dim]edit[/]                            $EDITOR on current epic/story description

[bold]TASKS[/]   [italic dim]task IDs are 1-indexed per story[/]
  [green]task add "Wire OAuth callback"[/]
  [green]task done 2[/]                     mark #2 complete  ([green]task undone 2[/] reopens)
  [green]task edit 2 "New title"[/]
  [green]task delete 2[/]

[bold]COMMENTS[/]
  [yellow]comment add "Picked this back up"[/]    inline
  [yellow]comment add[/]                          opens $EDITOR

[bold]CREATE[/]   [italic dim]scaffolds locally with NEW-N key — `push` (Phase 6) creates the real Jira issue[/]
  [cyan]epic create "Auth overhaul" --priority high --label security[/]
  [magenta]story create "SSO integration" --epic KAN-4 --priority high[/]
  [magenta]story create "Welcome screen"[/]            auto-links to epic when run inside one
  [green]task add "Wire OAuth callback"[/]      add a sub-task to the current story

[bold]DELETE[/]   [italic dim]soft-marks with `_deleted: true` — `push` removes from Jira; NEW-* items are removed immediately[/]
  [cyan]epic delete KAN-4[/]                  cascades to child stories
  [magenta]story delete KAN-5[/]
  [green]task delete 2[/]                       removed immediately (sub-task issue deleted on push)
  [dim]epic undelete KAN-4[/]                clear the deletion mark
  [dim]story undelete KAN-5[/]

[bold]SYNC[/]
  [yellow]status[/]                          summary of all dirty items (created/modified/deleted)
  [yellow]diff[/]                            opens a viewer (Esc to return); pick files with ↑/↓
  [yellow]diff KAN-5[/]                      inline diff for one item
  [dim]push[/] [dim]/[/] [dim]pull[/]                      sync with Jira (Phase 6/7)

[bold]SHELL[/]
  ↑[dim]/[/]↓        command history          →     accept ghost suggestion
  PgUp[dim]/[/]PgDn  scroll output            wheel scroll output (mouse)
  Ctrl-L     clear screen             Ctrl-D[dim]/[/]exit  quit
  [dim]Append --help to any command for flag details.[/]""")


def _project_from_url(base_url: str) -> str:
    try:
        return base_url.split("//", 1)[-1].split(".", 1)[0]
    except (IndexError, AttributeError):
        return "?"


def _collect_known_commands(typer_app: "typer.Typer") -> set[str]:
    """Union of typer top-level commands + REPL builtins. Used to short-circuit unknown input."""
    from typer.main import get_command

    builtins = {"cd", "pwd", "clear", "help", "exit", "quit", ":q"}
    return set(get_command(typer_app).commands.keys()) | builtins


def run_tui(typer_app: "typer.Typer") -> int:
    """Launch the Textual app. Returns the desired process exit code."""
    PMShell(typer_app).run()
    return 0
