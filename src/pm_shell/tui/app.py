"""Textual chat-style shell. Commands dispatch through the same typer engine
the one-shot CLI uses; output is captured and rendered into the log as
ANSI-decoded Text so colours survive."""

from __future__ import annotations

import difflib
import os
import shlex
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Optional

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
from pm_shell.branding import banner as _render_banner, project_from_url
from pm_shell.config import ConfigNotFoundError, load_config, workspace_dir
from pm_shell.io import console, err_console
from pm_shell.shell.completion import PMCompleter
from pm_shell.workspace.paths import resolve_context, resolve_workspace_target

if TYPE_CHECKING:
    import typer

_EXIT_WORDS = {"exit", "quit", ":q"}

_KIND_COLOR = {"created": "green", "modified": "yellow", "deleted": "red"}


class PMInput(Input):
    # Tab accepts the ghost-text suggestion (→ already does this by default).
    BINDINGS = [
        Binding("tab", "cursor_right", show=False, priority=True),
    ]


class PMLog(RichLog):
    # Clicks fall through to the prompt instead of stealing focus.
    can_focus = False


class PMSuggester(Suggester):
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

    ENABLE_COMMAND_PALETTE = False

    BINDINGS = [
        Binding("ctrl+d", "quit", "quit", show=True),
        Binding("pageup", "scroll_log_up", "scroll", show=True),
        Binding("pagedown", "scroll_log_down", "", show=False),
        # No priority — keep ↑/↓ at the bottom of the chain so ListView
        # (in DiffScreen) handles them first.
        Binding("up", "history_back", "history", show=True),
        Binding("down", "history_forward", "", show=False),
    ]

    def __init__(self, typer_app: "typer.Typer") -> None:
        super().__init__()
        self.theme = "ansi-dark"
        self._typer_app = typer_app
        self._suggester = PMSuggester(typer_app)
        self._history: list[str] = []
        self._history_idx: Optional[int] = None
        self._original_cwd: Optional[Path] = None
        self._known_commands = _collect_known_commands(typer_app)
        # Routes next submitted line to this callback instead of dispatching it (y/n prompts).
        self._pending_input: Optional[Callable[[str], None]] = None

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
            log.write(_render_banner(
                version=__version__,
                project=project_from_url(cfg.base_url),
            ))
        except ConfigNotFoundError:
            log.write(_render_banner(version=__version__))
        self.query_one("#prompt", Input).focus()
        self._refresh_context()

    def on_unmount(self) -> None:
        if self._original_cwd is not None:
            try:
                os.chdir(self._original_cwd)
            except OSError:
                pass

    def _banner_text(self) -> str:
        # Banner is rendered into the log on_mount; this Static is reserved for future status.
        return ""

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
        raw = event.value
        event.input.value = ""

        log = self.query_one("#log", RichLog)

        if self._pending_input is not None:
            pending = self._pending_input
            self._pending_input = None
            echo = self._context_label().copy()
            echo.append(" ")
            echo.append(raw)
            log.write(echo)
            pending(raw.strip())
            return

        line = raw.strip()
        if not line:
            return

        self._history.append(line)
        self._history_idx = None

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
        if head == "merge" and "--help" not in rest and "-h" not in rest:
            self._handle_merge(rest)
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

    def _handle_merge(self, extra_args: list[str]) -> None:
        from pm_shell.sync.diff import compute_changes

        log = self.query_one("#log", RichLog)

        yes = "--yes" in extra_args or "-y" in extra_args
        dry_run = "--dry-run" in extra_args

        changes = compute_changes()
        if not changes:
            log.write(Text.from_markup("[dim]workspace is clean — nothing to merge[/dim]"))
            return

        log.write(self._merge_preview_text(changes, dry_run=dry_run))

        if yes or dry_run:
            self._run_merge_live(dry_run=dry_run)
            return

        log.write(Text.from_markup("[bold]Apply these changes to Jira?[/] [dim]\\[y/N][/]"))

        def on_answer(answer: str) -> None:
            if answer.lower() in ("y", "yes"):
                self._run_merge_live(dry_run=False)
            else:
                log.write(Text.from_markup("[yellow]merge cancelled[/yellow]"))

        self._pending_input = on_answer

    def _merge_preview_text(self, changes, *, dry_run: bool) -> Text:
        kinds = Counter(c.kind for c in changes)
        counts_line = ", ".join(f"[{_KIND_COLOR[k]}]{n} {k}[/]" for k, n in kinds.items())
        prefix = "[bold yellow]Dry run:[/] would merge" if dry_run else "[bold]Merge:[/]"
        return Text.from_markup(f"{prefix} {len(changes)} change(s) — {counts_line}")

    def _run_merge_live(self, *, dry_run: bool) -> None:
        log = self.query_one("#log", RichLog)

        try:
            cfg = load_config()
        except ConfigNotFoundError as exc:
            log.write(Text.from_markup(f"[red]merge halted:[/] {exc}"))
            return

        label = "dry run" if dry_run else "merge"
        log.write(Text.from_markup(f"[dim]starting {label}…[/dim]"))

        def worker() -> None:
            from pm_shell.sync.push import PushError, merge as run_merge

            def progress(msg: str) -> None:
                self.call_from_thread(log.write, Text.from_markup(f"  [dim]· {msg}[/dim]"))

            try:
                outcome = run_merge(cfg, dry_run=dry_run, progress=progress)
            except PushError as exc:
                self.call_from_thread(log.write, Text.from_markup(f"[red]merge halted:[/] {exc}"))
                return
            except Exception as exc:  # noqa: BLE001 — surface any unexpected failure
                self.call_from_thread(log.write, Text.from_markup(f"[red]merge error:[/] {exc!s}"))
                return

            self.call_from_thread(self._render_merge_outcome, outcome)

        self.run_worker(worker, thread=True, exclusive=True, group="merge")

    def _render_merge_outcome(self, outcome) -> None:
        log = self.query_one("#log", RichLog)
        for line in outcome.successes:
            log.write(Text.from_markup(f"  [green]✓[/] {line}"))
        for warn in outcome.warnings:
            log.write(Text.from_markup(f"  [yellow]![/] {warn}"))
        for label, err in outcome.failures:
            log.write(Text.from_markup(f"  [red]✗[/] [bold]{label}:[/] {err}"))

        if outcome.dry_run:
            log.write(Text.from_markup("[dim]dry run complete — no changes made.[/dim]"))
        elif outcome.failures:
            log.write(Text.from_markup(
                f"[yellow]merge finished with {len(outcome.failures)} failure(s);[/] "
                f"see [dim].jira/.log/push-*.json[/dim]"
            ))
        else:
            log.write(Text.from_markup(
                f"[green]merge complete — {len(outcome.successes)} operation(s) applied.[/green]"
            ))

        self._suggester.refresh()
        self._refresh_context()

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
  [dim]tree [KEY|path][/]                 the workspace tree (full or scoped)
  [dim]show[/]                            smart card for the current epic/story

[bold]NAVIGATE[/]   [italic dim]cd is key-aware — keys are unique IDs, no slug needed[/]
  [dim]cd KAN-4[/]                        into an epic
  [dim]cd KAN-5[/]                        into a story (resolves globally)
  [dim]cd ..[/]                           up one level (refuses to leave .jira)
  [dim]cd[/]                              workspace root

[bold]VIEW[/]
  [cyan]epic show[/] [dim][KEY][/]                  epic card + story list
  [cyan]epic list[/]                       table of all epics
  [magenta]story show[/] [dim][KEY][/]                 story card + tasks + latest comment
  [magenta]story list[/] [dim][--epic KEY][/]         story table (filtered by epic if given)
  [green]task list[/] [dim][STORY][/]                task table for a story
  [yellow]comment list[/] [dim][STORY][/]             all comments
  [yellow]comment last[/] [dim][STORY][/]             most recent comment only

[bold]EDIT[/]   [italic dim]all changes stay local — push (Phase 6) syncs them to Jira[/]

  [cyan]epic set[/] [dim][KEY][/]                   update fields on an epic
    [dim]--summary[/]      title
    [dim]--status[/]       todo | in-progress | done | blocked
    [dim]--priority[/]     low | medium | high | critical
    [dim]--owner[/]        user email (pass "" to clear)
    [dim]--label[/]        add a label (repeatable)
    [dim]--description[/]  inline (use `edit` for multi-line)

  [magenta]story set[/] [dim][KEY][/]                  update fields on a story
    [dim]--summary[/]      title
    [dim]--status[/]       todo | in-progress | done | blocked
    [dim]--priority[/]     low | medium | high | critical
    [dim]--assignee[/]     user email (pass "" to clear)
    [dim]--label[/]        add a label (repeatable)
    [dim]--description[/]  inline (use `edit` for multi-line)
    [dim]--epic[/]         reparent to a different epic key
    [dim]--points[/]       story points (integer)

  [magenta]start[/] [dim]/[/] [magenta]done[/] [dim]/[/] [magenta]block "reason"[/]   story status shortcuts (cwd-inferred)
  [dim]edit[/]                            open the current item's description in $EDITOR

[bold]TASKS[/]   [italic dim]task IDs are 1-indexed per story[/]
  [green]task add "Wire OAuth callback"[/]
  [green]task done 2[/]                     mark #2 complete   ([green]task undone 2[/] reopens)
  [green]task edit 2 "New title"[/]
  [green]task delete 2[/]                   removed immediately

[bold]COMMENTS[/]
  [yellow]comment add "..."[/]                inline append
  [yellow]comment add[/]                      opens $EDITOR

[bold]CREATE[/]   [italic dim]scaffolds with a NEW-N placeholder key — push creates the real Jira issue[/]

  [cyan]epic create "Summary"[/]              accepts: [dim]--priority --owner --label --description[/]
  [magenta]story create "Summary"[/]             accepts: [dim]--epic --priority --assignee --label \
--description --points[/]
                                  (auto-links to current epic when run inside one)

[bold]DELETE[/]   [italic dim]soft-marks `_deleted: true` — push removes from Jira; NEW-* items are removed immediately[/]
  [cyan]epic delete[/] [dim][KEY][/]                cascades to child stories
  [magenta]story delete[/] [dim][KEY][/]
  [green]task delete N[/]                    immediate (sub-task issue deleted on push)
  [dim]epic undelete / story undelete[/]   clear the deletion mark (epic cascades)

[bold]SYNC[/]
  [yellow]status[/]                          summary of all dirty items (created/modified/deleted)
  [yellow]diff[/]                            opens the diff viewer (Esc to return)
  [yellow]diff KAN-5[/]                      inline diff for one item

  [yellow]merge[/]                           push local changes to Jira (inline y/n prompt, then streams progress)
    [dim]--yes[/] / [dim]-y[/]                 skip the confirmation
    [dim]--dry-run[/]                  preview the API calls without contacting Jira
  [dim]pull[/]                            sync from Jira (Phase 7 — not yet)

[bold]SHELL[/]
  ↑[dim]/[/]↓        command history          →[dim]/[/]Tab  accept ghost suggestion
  PgUp[dim]/[/]PgDn  scroll output            wheel    scroll output (mouse)
  Ctrl-D[dim]/[/]exit  quit              [dim]`clear` empties the output log[/]
  [dim]Append --help to any command for the full flag list.[/]""")


def _collect_known_commands(typer_app: "typer.Typer") -> set[str]:
    from typer.main import get_command

    builtins = {"cd", "pwd", "clear", "help", "exit", "quit", ":q"}
    return set(get_command(typer_app).commands.keys()) | builtins


def run_tui(typer_app: "typer.Typer") -> int:
    PMShell(typer_app).run()
    return 0
