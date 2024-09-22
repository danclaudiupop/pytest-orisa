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
from textual.reactive import Reactive, var
from textual.widgets import (
    Button,
    LoadingIndicator,
    Tree,
)
from textual.widgets._tabbed_content import ContentTabs
from textual.widgets.tree import TreeNode
from textual.worker import Worker, get_current_worker

from pytest_orisa.cache import load_cache, write_cache
from pytest_orisa.components.code import CodeViewerScreen
from pytest_orisa.components.collection import TestsTree
from pytest_orisa.components.flags import PytestCliFlagsModal
from pytest_orisa.components.footer import OrisaFooter
from pytest_orisa.components.result import (
    GoToTest,
    RunContent,
    RunResult,
    TestSessionStatusBar,
)
from pytest_orisa.components.runbar import NodePreview, RunBar, RunButton
from pytest_orisa.domain import EventType, NodeType
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
            color: royalblue;
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
                        help=f"{node.data['type']} | {node.data['path']}",
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
        Binding("ctrl+x", "clear_all_runs", "Clear runs", priority=True),
        Binding("ctrl+e", "toggle_sidebar", "Toggle tests", priority=True),
        Binding("ctrl+i", "open_cli_flags", "CLI flags", priority=True),
    ]

    show_sidebar: Reactive[bool] = var(True)

    def __init__(self) -> None:
        super().__init__()
        self.event_dispatcher = EventDispatcher()
        self.current_selected_node: dict = {}
        self.pytest_cli_flags: list[tuple[str, bool]] = []
        self.current_run_worker: Worker | None = None

    async def on_load(self) -> None:
        self.start_event_dispatcher()
        await wait_for_server("localhost", 1337)
        self.pytest_cli_flags = load_cache() or []

    @work(thread=True, exclusive=True)
    def start_event_dispatcher(self) -> None:
        self.event_dispatcher.start()

    async def action_quit(self) -> None:
        self.event_dispatcher.stop()
        write_cache(self.pytest_cli_flags)
        await super().action_quit()

    def action_open_search(self) -> None:
        self.open_search()

    def action_open_cli_flags(self) -> None:
        self.open_cli_flags()

    def action_toggle_sidebar(self) -> None:
        self.show_sidebar = not self.show_sidebar

    def action_clear_all_runs(self) -> None:
        total_cleared = 0
        for widget in self.query(RunContent):
            total_cleared += widget.tab_count
            widget.clear_panes()

        self.tests_tree.reset_tree_labels()

        message = (
            f"[black on cyan] {total_cleared} [/] test runs cleared"
            if total_cleared
            else "No test runs to clear."
        )
        self.app.notify(message=message, severity="information")

    def watch_show_sidebar(self, show_sidebar: bool) -> None:
        self.set_class(show_sidebar, "-show-tree")

    def compose(self) -> ComposeResult:
        yield RunBar()
        with Horizontal():
            self.tests_tree = TestsTree("Tests", id="tree-view")
            yield self.tests_tree

            self.run_content = RunContent()
            self.run_content.border_title = "Test Results"
            yield self.run_content

        yield OrisaFooter()

    def open_search(self) -> None:
        if self.use_command_palette and not CommandPalette.is_open(self):
            self.push_screen(SearchCommandPalette())

    def open_cli_flags(self) -> None:
        if not any(
            isinstance(screen, PytestCliFlagsModal) for screen in self._screen_stack
        ):
            modal = PytestCliFlagsModal()
            self.push_screen(modal)

    def get_tree_node_by_pytest_nodeid(self, nodeid: str) -> TreeNode | None:
        return next(
            (
                node
                for node in self.tests_tree.tree_nodes.values()
                if node.data
                and isinstance(node.data, dict)
                and node.data["nodeid"] == nodeid
            ),
            None,
        )

    def select_node(self, node: TreeNode) -> None:
        self.tests_tree.scroll_to_node(node)
        self.tests_tree.select_node(node)

    @on(Button.Pressed, selector="#search")
    def on_search(self) -> None:
        self.open_search()

    @on(Button.Pressed, selector="#flags")
    def on_cli_flags(self) -> None:
        self.open_cli_flags()

    @on(Button.Pressed, selector="#show-code")
    def show_code(self) -> None:
        self.push_screen(
            CodeViewerScreen(
                name="code_viewer",
                current_selected_node=self.current_selected_node,
                location=self.build_breadcrumb_from_path(),
            ),
        )

    @on(GoToTest)
    def on_result_select_node(self, message: GoToTest) -> None:
        node = self.get_tree_node_by_pytest_nodeid(message.nodeid)
        if node:
            self.select_node(node)

    @on(Tree.NodeSelected)
    def on_node_select(self, event: Tree.NodeSelected) -> None:
        node_data = event.node.data
        if node_data is not None and self.current_selected_node != node_data:
            self.current_selected_node = node_data

            width_value = self.run_content.size.width - 10
            os.environ["ORISA_RUN_LOG_WIDTH"] = str(width_value)

        self.query_one(NodePreview).node_data = event.node.data

    @on(TestSessionStatusBar.CancelTestRun)
    def handle_cancel_test_run(self) -> None:
        if self.current_run_worker:
            self.current_run_worker.cancel()

    @on(RunButton.Pressed, selector="#run")
    async def on_run_triggered(self, event: RunButton.Pressed) -> None:
        run_result = RunResult()
        await self.run_content.push_new_pane(run_result)

        self.run_worker(
            self.run_node(
                run_result,
                run_button=cast(RunButton, event.button),
                pytest_cli_flags=self.pytest_cli_flags,
            ),
            exclusive=True,
            thread=True,
        )

        self.query(ContentTabs).last().focus()

    async def run_node(
        self,
        run_result: RunResult,
        run_button: RunButton,
        pytest_cli_flags: list[tuple[str, bool]],
    ) -> None:
        run_worker = get_current_worker()
        self.current_run_worker = run_worker

        process: Popen[str] = run_node(
            node=self.current_selected_node,
            pytest_cli_flags=pytest_cli_flags,
        )
        if process.stdout:
            with process.stdout:
                for line in iter(process.stdout.readline, ""):
                    if run_worker.is_cancelled:
                        process.terminate()
                        run_result.run_log.write_lines(
                            [
                                "".join(["-" * 80, "\n"]),
                                "Run cancelled \n",
                                "The test execution was interrupted.\n",
                                "".join(["-" * 80]),
                            ]
                        )
                        break
                    run_result.run_log.write_line(line)
        process.wait()

        if process.returncode != ExitCode.OK and process.stderr:
            with process.stderr:
                for line in iter(process.stderr.readline, ""):
                    run_result.run_log.write_line(line)

        run_button.reset()

        self.handle_process_result(
            process.returncode,
            run_result,
            self.current_selected_node,
        )

    def handle_process_result(
        self,
        returncode: int,
        run_result: RunResult,
        current_running_node: dict,
    ) -> None:
        if (
            returncode == ExitCode.USAGE_ERROR
            or returncode == ExitCode.NO_TESTS_COLLECTED
        ):
            self.handle_error()
        elif returncode == -15:
            self.handle_cancelled_run()
        elif returncode in (ExitCode.OK, ExitCode.TESTS_FAILED):
            self.handle_test_result(returncode, run_result, current_running_node)

    def handle_error(self) -> None:
        self.run_content.tab_color = "darkgrey"
        self.tests_tree.reset_tree_labels()
        self.query(TestSessionStatusBar).last().display = False

    def handle_cancelled_run(self) -> None:
        self.run_content.tab_color = "darkgrey"
        self.tests_tree.reset_tree_labels()
        self.app.notify(message="Run cancelled", severity="error", timeout=2)

    def handle_test_result(
        self,
        returncode: int,
        run_result: RunResult,
        current_running_node: dict,
    ) -> None:
        run_result.report = self.event_dispatcher.get_event_data(EventType.REPORT)

        if returncode == ExitCode.OK:
            status, color, severity = "PASSED", "cyan", "information"
        else:
            status, color, severity = "FAILED", "crimson", "error"

        self.run_content.tab_color = color
        self.app.notify(
            message=f"[{color}]{status}[/] {current_running_node['name']}",
            severity=severity,
            timeout=2,
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

        if self.current_selected_node["type"] != NodeType.DIR:
            node_name = f"⿻ {self.current_selected_node['name']}"
            if (
                self.current_selected_node["type"] == NodeType.FUNCTION
                and self.current_selected_node["parent_type"] == NodeType.CLASS
            ):
                return f"{breadcrumb} > {self.current_selected_node['parent_name']} > {node_name}"
            elif self.current_selected_node["type"] != NodeType.MODULE:
                return f"{breadcrumb} > {node_name}"

        return breadcrumb


if __name__ == "__main__":
    OrisaApp().run()
