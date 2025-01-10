import os
import subprocess
import time

import pytest
from _pytest import nodes
from _pytest._io import TerminalWriter
from _pytest.nodes import Node
from _pytest.terminal import TerminalReporter
from pytest import (
    Class,
    Config,
    Function,
    Session,
    TestReport,
)

from pytest_orisa.domain import (
    Event,
    EventType,
    NodeType,
)
from pytest_orisa.event_dispatcher import send_event


def pytest_addoption(parser) -> None:
    parser.addoption(
        "--disable-orisa",
        action="store_true",
        default=False,
        help="Enable Orisa plugin functionality",
    )


@pytest.hookimpl(trylast=True)
def pytest_configure(config: Config) -> None:
    if not config.getoption("--disable-orisa"):
        run_log_width = os.getenv("ORISA_RUN_LOG_WIDTH")
        if run_log_width is not None:
            run_log_width = int(run_log_width)

            terminal_writer: TerminalWriter = config.get_terminal_writer()
            terminal_writer.fullwidth = run_log_width
        config.pluginmanager.register(OrisaPlugin(config), "orisa_plugin")


class OrisaPlugin:
    def __init__(self, config: Config):
        self.config: Config = config

    @pytest.hookimpl(trylast=True)
    def pytest_runtest_logreport(self, report: TestReport):
        is_relevant = report.when == "call" or (
            report.when == "setup" and report.outcome in ["failed", "skipped"]
        )

        if not is_relevant:
            return

        send_event(
            Event(
                type=EventType.TEST_OUTCOME,
                data={
                    "nodeid": report.nodeid,
                    "status": report.outcome,
                },
            )
        )

    @pytest.hookimpl(tryfirst=True)
    def pytest_terminal_summary(
        self, terminalreporter: TerminalReporter, exitstatus: int, config: Config
    ) -> None:
        total_duration = time.time() - terminalreporter._sessionstarttime

        # Process empty category reports
        rest_results = {}
        if "" in terminalreporter.stats:
            for report in terminalreporter.stats[""]:
                nodeid = report.nodeid
                if nodeid not in rest_results:
                    rest_results[nodeid] = {}

                rest_results[nodeid][report.when] = {
                    "outcome": report.outcome,
                    "duration": report.duration,
                    "caplog": report.caplog,
                    "longreprtext": report.longreprtext,
                }

        stats = {
            "exit_code": str(exitstatus),
            "total_duration": total_duration,
            "test_results": {
                "rest": rest_results,
                **{
                    category: [
                        {
                            "nodeid": report.nodeid,
                            "outcome": report.outcome,
                            "duration": report.duration,
                            "caplog": report.caplog,
                            "longreprtext": report.longreprtext,
                            "when": report.when,
                            "capstderr": report.capstderr,
                            "skip_reason": str(report.longrepr[2])
                            if category == "skipped"
                            else "",
                        }
                        for report in reports
                    ]
                    for category, reports in terminalreporter.stats.items()
                    if category not in ["deselected", ""]
                },
            },
        }

        send_event(Event(type=EventType.REPORT, data=stats))

    @pytest.hookimpl(tryfirst=True)
    def pytest_collection_finish(self, session: Session) -> None:
        if session.config.getoption("--collect-only"):
            send_event(
                Event(
                    type=EventType.TESTS_COLLECTED,
                    data=build_pytest_tree(session.items),
                )
            )
        else:
            send_event(
                Event(
                    type=EventType.TESTS_SCHEDULED,
                    data=[item.nodeid for item in session.items],
                )
            )


def build_pytest_tree(items: list[nodes.Item]) -> dict:
    def create_node_data(
        node: Node, parent_type: str | None = None, parent_name: str | None = None
    ) -> dict:
        return {
            "name": node.name,
            "path": str(node.path),
            "type": type(node).__name__.upper(),
            "parent_type": parent_type,
            "parent_name": parent_name,
            "lineno": node.reportinfo()[1]
            if isinstance(node, Class)
            else (node.location[1] if isinstance(node, Function) else 0),
            "nodeid": node.nodeid,
            "children": [],
        }

    def add_to_tree(
        nodes: list[Node],
        tree: dict,
        parent_type: str | None = None,
        parent_name: str | None = None,
    ) -> None:
        if not nodes:
            return

        node: Node = nodes.pop(0)
        node_data: dict = create_node_data(node, parent_type, parent_name)

        if "children" not in tree:
            tree["children"] = []

        existing_node = next(
            (child for child in tree["children"] if child["name"] == node_data["name"]),
            None,
        )
        if existing_node is None:
            tree["children"].append(node_data)
            existing_node = node_data

        add_to_tree(nodes, existing_node, type(node).__name__.upper(), node.name)

    tree: dict = {"data": {}, "meta": {"total": len(items)}}

    for item in items:
        needed_collectors: list[Node] = item.listchain()[1:]  # strip root node
        if needed_collectors:
            root_node = needed_collectors[0]
            root_name = root_node.name
            if root_name not in tree["data"]:
                tree["data"][root_name] = create_node_data(root_node)
            add_to_tree(
                needed_collectors[1:],
                tree["data"][root_name],
                type(root_node).__name__.upper(),
                root_name,
            )

    return tree


def collect_tests() -> None:
    try:
        subprocess.run(
            ["pytest", "--collect-only", "-q"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"pytest collection failed: {e}") from e
    except Exception as e:
        raise RuntimeError(f"An unexpected error occurred: {str(e)}") from e


def run_node(
    node: dict | None, pytest_cli_flags: list[tuple[str, bool]]
) -> subprocess.Popen[str]:
    if node is not None:
        if node["type"] == NodeType.FUNCTION and node["parent_type"] == NodeType.CLASS:
            path = f"{node['path']}::{node['parent_name']}::{node['name']}"
        elif node["type"] in [NodeType.CLASS, NodeType.FUNCTION]:
            path = f"{node['path']}::{node['name']}"
        else:
            path = node["path"]

        args: list[str] = []
        for flag, is_active in pytest_cli_flags:
            if is_active:
                args.append(flag)

    return subprocess.Popen(
        ["pytest", path, *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
