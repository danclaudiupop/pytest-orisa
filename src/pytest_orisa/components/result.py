from datetime import datetime
from typing import Sequence

from rich.syntax import Syntax
from textual import on
from textual.app import ComposeResult
from textual.containers import Grid, VerticalScroll
from textual.message import Message
from textual.reactive import Reactive, reactive, var
from textual.widgets import (
    Button,
    Collapsible,
    DataTable,
    Label,
    Log,
    TabbedContent,
    TabPane,
)


class GoToTest(Message):
    """A message to navigate to a specific test"""

    def __init__(self, nodeid: str) -> None:
        self.nodeid = nodeid
        super().__init__()


class PassedTestDataTable(DataTable):
    DEFAULT_CSS = """
        PassedTestDataTable {
            padding-bottom: 2;
        }
    """

    @on(DataTable.RowSelected)
    def go_to_test(self, event: DataTable.RowSelected) -> None:
        row_index: int = event.cursor_row
        nodeid: str = event.data_table.get_row_at(row_index)[0]
        self.post_message(GoToTest(nodeid))


class TestOutputDisplay(Label):
    DEFAULT_CSS = """
        TestOutputDisplay {
            & > Label {
                overflow: auto;
                width: 100%
            }

            & > Grid {
                height: 1;
                background: $panel;
                dock: bottom;
                margin-top: 1;

                & > #go-to-test {
                    dock: left;
                    background: darkgrey;
                }

                & > #copy-to-clipboard {
                    dock: right;
                    background: darkgrey;
                }

            }
        }
    """

    def __init__(self, content: Syntax, nodeid: str) -> None:
        self.content: Syntax = content
        self.nodeid: str = nodeid
        super().__init__(content)

    def compose(self) -> ComposeResult:
        yield Label(self.content)
        yield Grid(
            Button("✂ Copy output", id="copy-to-clipboard"),
            Button("↪  Go to test", id="go-to-test"),
        )

    @on(Button.Pressed, selector="#copy-to-clipboard")
    def copy_output(self) -> None:
        self.app.copy_to_clipboard(self.content.code)
        self.app.notify("Copied to clipboard", severity="warning")

    @on(Button.Pressed, selector="#go-to-test")
    def go_to_test(self) -> None:
        self.post_message(GoToTest(self.nodeid))


class TestSessionStatusBar(Grid):
    DEFAULT_CSS = """
        TestSessionStatusBar {
            height: 1;
            background: $panel;
            dock: bottom;
            margin-top: 1;

            & > #run-at {
                dock: left;
                color: $text-muted;
            }

            & > #action-button {
                dock: right;
                background: yellow;
            }
        }
    """

    class CancelTestRun(Message):
        """A message to request cancellation of the current test run."""

    def __init__(self, lines: Sequence[str]) -> None:
        super().__init__()
        self.lines = lines
        self.test_session_is_running = True

    def compose(self) -> ComposeResult:
        yield Label(
            f" Test run at {datetime.now().strftime('%m/%d/%Y, %I:%M:%S %p')}",
            id="run-at",
        )
        yield Button("Cancel", id="action-button")

    @property
    def action_button(self) -> Button:
        return self.query_one("#action-button", Button)

    def test_session_finished(self) -> None:
        self.test_session_is_running = False
        self.action_button.label = "✂ Copy output"
        self.action_button.styles.background = "darkgrey"

    @on(Button.Pressed, selector="#action-button")
    def handle_button_press(self) -> None:
        if self.test_session_is_running:
            self.post_message(self.CancelTestRun())
            self.action_button.styles.background = "grey"
            self.action_button.disabled = True
            self.action_button.label = "Canceled"
            self.app.notify(
                "Triggered cancellation of test run", severity="information", timeout=1
            )
        else:
            self.copy_test_output()

    def copy_test_output(self) -> None:
        self.app.copy_to_clipboard("\n".join(self.lines))
        self.app.notify("Copied to clipboard", severity="warning")


class RunResult(TabbedContent):
    DEFAULT_CSS = """
        RunResult {
            &.-running > ContentTabs {
                display: none;
            }

            & > ContentSwitcher{
                padding-bottom: -1;

                & > TabPane Collapsible {
                    overflow-x: auto;
                    padding-top: -1;

                    & > Contents {
                        width: 100%;
                        height: auto;
                        padding: 0 1;
                        border: solid grey 50%;
                        background: $background;

                    }

                    & > CollapsibleTitle:hover {
                        background: $primary 90%;
                    }

                    & > CollapsibleTitle:focus {
                        background: $primary 95%;
                    }
                }

                & > TabPane Log {
                    overflow: auto;
                    background: $background;
                }
            }
        }
    """

    run_log: Reactive[Log] = var(Log, init=True)
    report: Reactive[dict | None] = reactive(None, init=False)

    async def on_mount(self) -> None:
        await self.add_pane(TabPane("running", self.run_log, id="summary"))
        self.get_pane("summary").mount(TestSessionStatusBar(lines=self.run_log.lines))
        self.add_class("-running")

    async def watch_report(self, report: dict) -> None:
        self.remove_class("-running")
        self.update_summary_tab(report)
        self.query_one(TestSessionStatusBar).test_session_finished()
        await self.push_passed_tests(report)
        await self.push_failed_tests(report)
        await self.push_live_logs(report)

    def update_summary_tab(self, report: dict) -> None:
        self.get_tab(
            "summary"
        ).label = f"[black on white] {report['meta']['total']} [/] tests"

    async def push_failed_tests(self, report: dict) -> None:
        failed_reports: list[dict] = report["failed"]

        if not failed_reports:
            return

        entries: list[Collapsible] = []
        for report in failed_reports:
            content = Syntax(
                report["longreprtext"] + report["capstderr"] + report["caplog"],
                "python",
                theme="ansi_dark",
            )
            entries.append(
                Collapsible(
                    TestOutputDisplay(content, nodeid=report["nodeid"]),
                    title=report["nodeid"],
                )
            )

        await self.add_pane(
            TabPane(
                f"[black on red] {len(failed_reports)} [/] failed",
                VerticalScroll(*entries),
            )
        )

    async def push_passed_tests(self, report: dict) -> None:
        passed_reports: list[dict] = report["passed"]

        if not passed_reports:
            return

        table = PassedTestDataTable(cursor_type="row")
        table.add_columns(
            *(
                "Test",
                "Setup duration",
                "Call duration",
                "Teardown duration",
                "Nr. of fixtures used",
            )
        )

        for passed in passed_reports:
            setup_duration = report["setup_durations"].get(passed["nodeid"])
            teardown_duration = report["teardown_durations"].get(passed["nodeid"])

            table.add_row(
                *(
                    passed["nodeid"],
                    f"{setup_duration:.2f}",
                    f"{passed['duration']:.2f}",
                    f"{teardown_duration:.2f}",
                    len(passed["fixtures_used"]),
                )
            )

        await self.add_pane(
            TabPane(
                f"[black on green] {len(passed_reports)} [/] passed",
                VerticalScroll(table),
            )
        )

    async def push_live_logs(self, report: dict) -> None:
        passed_reports: list[dict] = report["passed"]

        logs_entries: list[Collapsible] = []
        for test_report in passed_reports:
            if test_report.get("longreprtext") or test_report.get("caplog"):
                content = Syntax(
                    test_report.get("longreprtext", "") + test_report.get("caplog", ""),
                    "KernelLogLexer",
                    theme="ansi_dark",
                )
                logs_entries.append(
                    Collapsible(
                        TestOutputDisplay(content, nodeid=test_report["nodeid"]),
                        title=test_report["nodeid"],
                    )
                )

        if logs_entries:
            await self.add_pane(
                TabPane(
                    f"[black on blue] {len(logs_entries)} [/] live logs",
                    VerticalScroll(*logs_entries),
                )
            )


class RunContent(TabbedContent):
    DEFAULT_CSS = """
        RunContent {
            background: $background;
            border: solid grey;
            border-title-align: left;
            height: 100%;
            padding-top: 1;
        }
    """

    tab_color: Reactive[str] = reactive("cyan", always_update=True)
    latest_active: var[str | None] = var(None, init=False)

    def watch_tab_color(self, tab_color: str) -> None:
        if self.latest_active:
            tab = self.get_tab(self.latest_active)
            tab.styles.background = tab_color
            tab.styles.animate("opacity", value=0.95, duration=0.9)

    async def push_new_pane(self, run_result: RunResult) -> None:
        n: int = self.tab_count + 1
        pane = TabPane(f"Run #{n} ", run_result, id=f"tab-{n}")
        before = None if self.tab_count == 0 else f"tab-{n-1}"
        await self.add_pane(pane, before=before)
        self.active = f"tab-{n}"
        self.latest_active = self.active
        active_tab = self.get_tab(self.active)
        active_tab.styles.margin = (0, 1, 0, 1)
        active_tab.styles.background = "ansi_bright_yellow"
