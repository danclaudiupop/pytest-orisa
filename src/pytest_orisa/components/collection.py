from typing import TYPE_CHECKING, cast

from textual import on
from textual.message import Message
from textual.reactive import var
from textual.widgets import Tree
from textual.widgets.tree import NodeID, TreeNode

from pytest_orisa.plugin import collect_tests

if TYPE_CHECKING:
    from pytest_orisa.app import OrisaApp


class TestsTree(Tree):
    DEFAULT_CSS = """
        TestsTree {
            background: $background;
            display: none;
            scrollbar-gutter: stable;
            overflow: auto;
            width: auto;
            min-width: 20%;
            height: 100%;
            dock: left;
            border: solid grey;
            padding: 1;

            & > .tree--guides {
                color: $primary;
            }

            & > .tree--guides-selected {
                color: $primary;
            }

            & > .tree--cursor {
                background: $primary;
            }

            & > .tree--guides-hover {
                color: $primary;
            }

            &:focus > .tree--cursor {
                background: $primary;
            }
        }
    """

    auto_expand = var(False)
    show_root = var(False)

    class EventTestsCollected(Message):
        def __init__(self, data: dict) -> None:
            super().__init__()
            self.data: dict = data

    def on_mount(self) -> None:
        self.orisa.event_dispatcher.register_handler(
            event_type="tests_collected",
            handler=lambda data: self.post_message(self.EventTestsCollected(data)),
        )
        collect_tests()

    @on(EventTestsCollected)
    async def on_tests_collected(self, event: EventTestsCollected) -> None:
        tests_collected: dict = event.data
        if tests_collected is not None:
            self.clear()
            self.loading = True
            await self.update_tree(
                plugin_pytest_tree=tests_collected["data"], parent=self.root
            )
            self.loading = False
            self.border_title = (
                f"Tests [black on white ] {tests_collected['meta']['total']} [/]"
            )

    async def update_tree(
        self, *, plugin_pytest_tree: dict, parent: TreeNode | Tree
    ) -> None:
        if isinstance(parent, Tree):
            parent = parent.root

        def add_children(children: list, parent_node: TreeNode) -> None:
            for child in children:
                has_children: bool = "children" in child and child["children"]
                if has_children:
                    node: TreeNode = parent_node.add(
                        child["name"], expand=True, data=child
                    )
                    add_children(child["children"], node)
                else:
                    parent_node.add_leaf(child["name"], data=child)

        for key, value in plugin_pytest_tree.items():
            if isinstance(value, dict) and "children" in value and value["children"]:
                node: TreeNode = parent.add(key, expand=True, data=value)
                self.select_node(node)
                add_children(value["children"], node)
            else:
                parent.add_leaf(key, data=key)

    @property
    def tree_nodes(self) -> dict[NodeID, TreeNode]:
        return self._tree_nodes

    @property
    def orisa(self) -> "OrisaApp":
        return cast("OrisaApp", self.app)


class TreeLabelUpdater:
    def __init__(self, tests_tree: "TestsTree", current_running_node: dict) -> None:
        self.tests_tree: "TestsTree" = tests_tree
        self.current_running_node: dict = current_running_node
        self.node: TreeNode | None = None
        self.report: dict | None = None
        self.error_occurred: bool = False

    def __enter__(self) -> "TreeLabelUpdater":
        # Don't update nodes here, just find the node
        self.node = self.find_node()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if not self.error_occurred and self.node:
            self.update_node("[yellow]⧗[/] ")  # Update node only if no error occurred
        if self.report is not None and not self.error_occurred:
            self._update_final_labels()

    def mark_error_state(self) -> None:
        self.error_occurred = True

    def find_node(self) -> TreeNode | None:
        for node in self.tests_tree.tree_nodes.values():
            if (
                node.data
                and isinstance(node.data, dict)
                and node.data.get("nodeid") == self.current_running_node.get("nodeid")
            ):
                return node
        return None

    def update_node(self, status: str) -> None:
        if self.node:
            self.update_node_and_children(self.node, status, intermediate=True)

    def update_node_and_children(
        self,
        node: TreeNode,
        status: str,
        intermediate: bool = False,
        results: dict | None = None,
    ) -> None:
        if intermediate:
            node.label = f"{node.data['name']} {status}"
        else:
            outcome = results.get(node.data.get("nodeid")) if results else None
            if outcome:
                status = self.get_status_icon(outcome)
                node.label = f"{node.data['name']} {status}"
            else:
                node.label = node.data["name"]

        for child in node.children:
            self.update_node_and_children(child, status, intermediate, results)

    def _update_final_labels(self) -> None:
        if not self.node:
            return

        results = self.extract_results_from_report()
        self.update_node_and_children(
            self.node, status="", intermediate=False, results=results
        )

    def extract_results_from_report(self) -> dict:
        results: dict = {}
        for outcome in ["passed", "failed", "skipped", "xfailed"]:
            for test in self.report.get(outcome, []) if self.report else []:
                results[test.get("nodeid")] = outcome
        return results

    @staticmethod
    def get_status_icon(outcome: str) -> str:
        icons: dict[str, str] = {
            "passed": "[green]●[/] ",
            "failed": "[red]✖[/] ",
            "skipped": "[yellow]-[/] ",
        }
        return icons.get(outcome, "")
