from typing import TYPE_CHECKING, cast

from textual.reactive import var
from textual.widgets import Tree
from textual.widgets.tree import NodeID, TreeNode

from pytest_orisa.domain import EventType
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

            & > .tree--guides,
            & > .tree--guides-hover,
            & > .tree--guides-selected {
                color: $primary;
            }

            & > .tree--cursor,
            &:focus > .tree--cursor {
                background: $primary;
            }
        }
    """

    auto_expand = var(False)
    show_root = var(False)

    def on_mount(self) -> None:
        self.orisa.event_dispatcher.register_handler(
            event_type=EventType.TESTS_COLLECTED,
            handler=lambda data: self.build_tree(data),
        )
        self.orisa.event_dispatcher.register_handler(
            event_type=EventType.TESTS_SCHEDULED,
            handler=lambda nodeids: self.mark_tests_as_running(nodeids),
        )
        self.orisa.event_dispatcher.register_handler(
            event_type=EventType.TEST_OUTCOME,
            handler=lambda data: self.update_test_outcome(data),
        )
        collect_tests()

    def build_tree(self, data: dict) -> None:
        if data is not None:
            self.clear()
            self.loading = True
            self.update_tree(plugin_pytest_tree=data["data"], parent=self.root)
            self.loading = False
            self.border_title = f"Tests [black on white ] {data['meta']['total']} [/]"

    def update_tree(self, *, plugin_pytest_tree: dict, parent: TreeNode | Tree) -> None:
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

    def mark_tests_as_running(self, nodeids: list[str]) -> None:
        for node in self.tree_nodes.values():
            if (
                node.data
                and isinstance(node.data, dict)
                and node.data.get("nodeid") in nodeids
            ):
                node.label = f"{node.data['name']} [yellow]⧗ [/]"

    def update_test_outcome(self, data: dict) -> None:
        for node in self.tree_nodes.values():
            if (
                node.data
                and isinstance(node.data, dict)
                and node.data.get("nodeid") == data.get("nodeid")
            ):
                status = data.get("status", "")
                if status == "passed":
                    node.label = f"{node.data['name']} [green]● [/] [grey58]{data.get('duration'):.1f}s[/]"
                elif status == "failed":
                    node.label = f"{node.data['name']} [red]✖ [/]"
                elif status == "skipped":
                    node.label = f"{node.data['name']} [yellow]◉ [/]"

    def reset_tree_labels(self) -> None:
        for node in self.tree_nodes.values():
            if node.data and isinstance(node.data, dict):
                node.label = node.data["name"]

    @property
    def tree_nodes(self) -> dict[NodeID, TreeNode]:
        return self._tree_nodes

    @property
    def orisa(self) -> "OrisaApp":
        return cast("OrisaApp", self.app)
