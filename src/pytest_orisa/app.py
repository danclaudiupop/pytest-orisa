import os
from functools import partial
from pathlib import Path
from subprocess import Popen
from typing import cast

from pytest import ExitCode
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.command import (
    CommandInput,
    CommandList,
    CommandPalette,
    Hit,
    Hits,
    Provider,
)
from textual.containers import (
    Horizontal,
    Vertical,
)
from textual.fuzzy import Matcher
from textual.notifications import SeverityLevel
from textual.reactive import Reactive, var
from textual.widgets import (
    Button,
    Footer,
    LoadingIndicator,
    Tree,
)
from textual.widgets._tabbed_content import ContentTabs
from textual.widgets.tree import TreeNode

from pytest_orisa.components.code import CodeViewerScreen
from pytest_orisa.components.collection import TestsTree, TreeLabelUpdater
from pytest_orisa.components.header import AppHeader, RunButton
from pytest_orisa.components.result import RunContent, RunResult
from pytest_orisa.event_dispatcher import (
    EventDispatcher,
    wait_for_server,
)
from pytest_orisa.plugin import run_node


class SearchCommandPalette(CommandPalette):
    DEFAULT_CSS = """
        SearchCommandPalette > Vertical {
            margin-top: 3; 
            height: 100%;
            visibility: hidden;
            background: $panel;
        }

        SearchCommandPalette:dark > .command-palette--highlight {
            text-style: bold;
            color: hotpink;
        }
    """

    def compose(self) -> ComposeResult:
        with Vertical():
            with Horizontal(id="--input"):
                yield CommandInput(placeholder="Search for tests …")
                if not self.run_on_select:
                    yield Button("\u25b6")
            with Vertical(id="--results"):
                yield CommandList()
                yield LoadingIndicator()


class SearchTestsCommands(Provider):
    async def search(self, query: str) -> Hits:
        matcher: Matcher = self.matcher(query)
        app: App = self.orisa

        for node in app.tests_tree.tree_nodes.values():
            if node.data and isinstance(node.data, dict):
                score = matcher.match(node.data["name"])
                if score > 0:
                    yield Hit(
                        score,
                        matcher.highlight(node.data["name"]),
                        partial(app.select_node, node),
                        help=f"{node.data["type"]} | {node.data["path"]}",
                    )

    @property
    def orisa(self) -> "OrisaApp":
        return cast("OrisaApp", self.app)


class OrisaApp(App):
    COMMANDS = {SearchTestsCommands}
    CSS_PATH = Path(__file__).parent / "orisa.tcss"

    BINDINGS: list[Binding] = [
        Binding("ctrl+q", "quit", "Quit", priority=True),
        Binding("ctrl+f", "open_search", "Search", priority=True),
        Binding("ctrl+x", "clear_all_runs", "Clear all runs", priority=True),
        Binding("ctrl+e", "toggle_sidebar", "Toggle tests", priority=True),
    ]

    show_sidebar: Reactive[bool] = var(True)

    def __init__(self) -> None:
        super().__init__()
        self.event_dispatcher = EventDispatcher()
        self.current_selected_node: dict = {}
        self.pytest_cli_flags: list[tuple[str, bool]] = []

    async def on_load(self) -> None:
        self.start_event_dispatcher()
        await wait_for_server("localhost", 1337)

    @work(thread=True, exclusive=True)
    def start_event_dispatcher(self) -> None:
        self.event_dispatcher.start()

    async def action_quit(self) -> None:
        self.event_dispatcher.stop()
        await super().action_quit()

    def action_open_search(self) -> None:
        self.open_search()

    def action_toggle_sidebar(self) -> None:
        self.show_sidebar = not self.show_sidebar

    def action_clear_all_runs(self) -> None:
        # clear the results
        total_cleared = 0
        for widget in self.query(RunContent):
            total_cleared += widget.tab_count
            widget.clear_panes()

        # clear the tree results
        for node in self.tests_tree.tree_nodes.values():
            if node.data and isinstance(node.data, dict):
                node.label = node.data["name"]

        message = (
            f"Cleared all test runs. [black on cyan] {total_cleared} [/] in total."
            if total_cleared
            else "No test runs to clear."
        )
        self.app.notify(message=message, severity="information")

    def watch_show_sidebar(self, show_sidebar: bool) -> None:
        self.set_class(show_sidebar, "-show-tree")

    def compose(self) -> ComposeResult:
        yield AppHeader()

        with Horizontal():
            self.tests_tree = TestsTree("Tests", id="tree-view")
            yield self.tests_tree

            with Vertical():
                self.run_content = RunContent()
                self.run_content.border_title = "Test Results"
                yield self.run_content

        yield Footer()

    def open_search(self) -> None:
        if self.use_command_palette and not CommandPalette.is_open(self):
            self.push_screen(SearchCommandPalette())

    @on(Button.Pressed, selector="#search-tests")
    def on_search(self) -> None:
        self.open_search()

    @on(Button.Pressed, selector="#show-code")
    def show_code(self) -> None:
        self.push_screen(
            CodeViewerScreen(
                name="code_viewer",
                current_selected_node=self.current_selected_node,
                location=self.build_breadcrumb_from_path(),
            ),
        )

    def get_tree_node_by_pytest_nodeid(self, nodeid: str) -> TreeNode | None:
        for node in self.tests_tree.tree_nodes.values():
            if node.data and isinstance(node.data, dict):
                if node.data["nodeid"] == nodeid:
                    return node

    def select_node(self, node: TreeNode) -> None:
        self.tests_tree.scroll_to_node(node)
        self.tests_tree.select_node(node)

    @on(Tree.NodeSelected)
    def on_node_select(self, event: Tree.NodeSelected) -> None:
        node_data = event.node.data
        if node_data is not None and self.current_selected_node != node_data:
            self.current_selected_node = node_data

            width_value = self.run_content.size.width - 10
            os.environ["ORISA_RUN_LOG_WIDTH"] = str(width_value)

    @on(Tree.NodeHighlighted)
    def on_node_highlight(self, event: Tree.NodeHighlighted) -> None:
        self.tests_tree.node_preview.node_data = event.node.data

    @on(RunButton.Pressed, selector="#run")
    async def on_run_triggered(self, event: RunButton.Pressed) -> None:
        run_result = RunResult()
        await self.run_content.push_new_pane(run_result)

        self.run_worker(
            self._run_node(
                run_result,
                button=cast(RunButton, event.button),
                pytest_cli_flags=self.pytest_cli_flags,
            ),
            exclusive=True,
            thread=True,
        )

        self.query(ContentTabs).last().focus()

    async def _run_node(
        self,
        run_result: RunResult,
        button: RunButton,
        pytest_cli_flags: list[tuple[str, bool]],
    ) -> None:
        current_running_node: dict = self.current_selected_node

        with TreeLabelUpdater(
            self.tests_tree, current_running_node
        ) as tree_label_updater:
            process: Popen[str] = run_node(
                node=self.current_selected_node,
                pytest_cli_flags=pytest_cli_flags,
            )
            if process.stdout:
                with process.stdout:
                    for line in iter(process.stdout.readline, ""):
                        run_result.run_log.write_line(line)
            process.wait()

            if process.returncode != 0 and process.stderr:
                with process.stderr:
                    for line in iter(process.stderr.readline, ""):
                        run_result.run_log.write_line(line)

            report: dict = self.event_dispatcher.get_event_data("report")
            run_result.report = report

            exit_status: ExitCode = report["meta"]["exit_status"]
            tree_label_updater.exit_status = exit_status
            tree_label_updater.report = report
            self.run_content.exit_status = exit_status
            self.push_run_notification(exit_status, current_running_node)
            button.reset()

    def push_run_notification(
        self, exit_status: ExitCode, current_running_node: dict
    ) -> None:
        possible_outcomes: dict = {
            ExitCode.OK: {
                "message": f"[cyan]PASSED[/] {current_running_node['name']}",
                "severity": "information",
            },
            ExitCode.TESTS_FAILED: {
                "message": f"[crimson]FAILED[/] {current_running_node['name']}",
                "severity": "error",
            },
            ExitCode.INTERRUPTED: {
                "message": f"[crimson]INTERRUPTED[/] {current_running_node['name']}",
                "severity": "error",
            },
            ExitCode.INTERNAL_ERROR: {
                "message": f"[crimson]INTERNAL ERROR[/] {current_running_node['name']}",
                "severity": "error",
            },
            ExitCode.USAGE_ERROR: {
                "message": f"[crimson]USAGE ERROR[/] {current_running_node['name']}",
                "severity": "error",
            },
            ExitCode.NO_TESTS_COLLECTED: {
                "message": f"[crimson]NO TESTS COLLECTED[/] {current_running_node['name']}",
                "severity": "error",
            },
        }

        outcome: dict[str, SeverityLevel] = possible_outcomes[exit_status]

        self.app.notify(
            message=outcome["message"], severity=outcome["severity"], timeout=2
        )

    def build_breadcrumb_from_path(self) -> str:
        start_root = (
            self.tests_tree.root.children[0] if self.tests_tree.root.children else None
        )

        path = self.current_selected_node["path"].split("/")
        if not start_root or not start_root.data:
            return ""

        try:
            start_root_index = path.index(start_root.data["name"])
        except ValueError:
            return ""

        sliced_path = path[start_root_index:]
        breadcrumb = " > ".join(sliced_path) if len(sliced_path) > 1 else sliced_path[0]

        if self.current_selected_node["type"] != "DIR":
            node_name = f"⿻ {self.current_selected_node['name']}"
            if (
                self.current_selected_node["type"] == "FUNCTION"
                and self.current_selected_node["parent_type"] == "CLASS"
            ):
                return f"{breadcrumb} > {self.current_selected_node['parent_name']} > {node_name}"
            return f"{breadcrumb} > {node_name}"

        return breadcrumb


if __name__ == "__main__":
    OrisaApp().run()
