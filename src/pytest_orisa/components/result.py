from datetime import datetime
from typing import Sequence

from pytest import ExitCode
from rich.syntax import Syntax
from textual import on
from textual.app import ComposeResult
from textual.containers import Grid, VerticalScroll
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
        self.app.select_node(self.app.get_tree_node_by_pytest_nodeid(nodeid))


class FailedTestTraceback(Label):
    DEFAULT_CSS = """
        FailedTestTraceback {
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
    def copy_traceback(self) -> None:
        self.app.copy_to_clipboard(self.content.code)
        self.app.notify("Copied to clipboard", severity="warning")

    @on(Button.Pressed, selector="#go-to-test")
    def go_to_test(self) -> None:
        self.app.select_node(self.app.get_tree_node_by_pytest_nodeid(self.nodeid))


class SummaryStatsBar(Grid):
    DEFAULT_CSS = """
        SummaryStatsBar {
            height: 1;
            background: $panel;
            dock: bottom;
            margin-top: 1;

            & > #run-at {
                dock: left;
                color: $text-muted;
            }

            & > #copy-to-clipboard {
                dock: right;
                background: darkgrey;
            }
        }
    """

    def __init__(self, lines: Sequence[str]) -> None:
        super().__init__()
        self.lines = lines

    def compose(self) -> ComposeResult:
        yield Label(
            f" Test run at {datetime.now().strftime("%m/%d/%Y, %I:%M:%S %p")}",
            id="run-at",
        )
        yield Button("✂ Copy output", id="copy-to-clipboard")

    @on(Button.Pressed, selector="#copy-to-clipboard")
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
        self.add_class("-running")

    async def watch_report(self, report: dict) -> None:
        self.remove_class("-running")
        self.update_summary_tab(report)
        await self.push_passed_tests(report)
        await self.push_failed_tests(report)

    def update_summary_tab(self, report: dict) -> None:
        self.get_tab(
            "summary"
        ).label = f"[black on white] {report["meta"]["total"]} [/] tests"
        self.get_pane("summary").mount(SummaryStatsBar(lines=self.run_log.lines))

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
                    FailedTestTraceback(content, nodeid=report["nodeid"]),
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


class RunContent(TabbedContent):
    DEFAULT_CSS = """
        RunContent {
            background: $background;
            border: grey;
            border-title-align: left;
            height: 100%;
            padding-top: 1;
        }
    """

    exit_status: Reactive[int] = reactive(0, always_update=True)
    latest_active: var[str | None] = var(None, init=False)

    def watch_exit_status(self, exit_status: ExitCode) -> None:
        if self.latest_active:
            tab = self.get_tab(self.latest_active)
            tab.styles.background = "cyan" if exit_status == 0 else "crimson"
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
