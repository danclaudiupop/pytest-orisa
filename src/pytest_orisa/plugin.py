import logging
import os
import subprocess
import time
from dataclasses import asdict
from typing import Any, Generator

import pytest
from _pytest import nodes
from _pytest._io import TerminalWriter
from _pytest.nodes import Node
from _pytest.reports import TestReport
from pytest import (
    CallInfo,
    Class,
    Config,
    ExitCode,
    Function,
    Item,
    Session,
)

from pytest_orisa.domain import Event, EventType, NodeType, Report, TestItem
from pytest_orisa.event_dispatcher import send_event

logging.basicConfig(level=logging.ERROR)
logger: logging.Logger = logging.getLogger(__name__)


REPORT = Report()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(
    item: Item, call: CallInfo[None]
) -> Generator[None, Any, None]:
    if item.config.getoption("--enable-orisa"):
        outcome = yield
        report: TestReport = outcome.get_result()
        nodeid = report.nodeid

        test_item = next(
            (
                t
                for t in REPORT.passed + REPORT.failed + REPORT.skipped + REPORT.xfailed
                if t.nodeid == nodeid
            ),
            None,
        )
        if test_item is None:
            test_item = TestItem(nodeid=nodeid)

        if report.skipped:
            test_item.status = "skipped"
            test_item.skip_reason = str(report.longrepr[2]) if report.longrepr else ""  # type: ignore
            REPORT.skipped.append(test_item)

        elif report.when == "call":
            test_item.call_duration = report.duration

            if report.passed:
                test_item.status = "passed"
                test_item.fixtures = [
                    {
                        "argname": argname,
                        "scope": fixture[0].scope,
                    }
                    for argname, fixture in item._fixtureinfo.name2fixturedefs.items()
                ]
                test_item.caplog = report.caplog
                REPORT.passed.append(test_item)

            elif report.failed:
                test_item.status = "failed"
                test_item.longreprtext = report.longreprtext
                test_item.capstderr = report.capstderr
                test_item.caplog = report.caplog
                REPORT.failed.append(test_item)

    else:
        yield


@pytest.hookimpl(trylast=True)
def pytest_runtest_logfinish(nodeid: str, location: tuple) -> None:
    test_item: TestItem | None = REPORT.get_test_item_by_nodeid(nodeid)
    if test_item is not None:
        send_event(
            Event(
                type=EventType.TEST_OUTCOME,
                data={
                    "nodeid": nodeid,
                    "status": test_item.status,
                    "duration": (
                        test_item.call_duration
                        + REPORT.setup_durations[nodeid]
                        + REPORT.teardown_durations[nodeid]
                    )
                    if test_item.status == "passed"
                    else None,
                },
            )
        )


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_setup(item: Item) -> Generator:
    if item.config.getoption("--enable-orisa"):
        nodeid = item.nodeid
        start_time = time.time()
        yield
        end_time = time.time()
        REPORT.setup_durations[nodeid] = end_time - start_time
    else:
        yield


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_teardown(item: Item) -> Generator:
    if item.config.getoption("--enable-orisa"):
        nodeid = item.nodeid
        start_time = time.time()
        yield
        end_time = time.time()
        REPORT.teardown_durations[nodeid] = end_time - start_time
    else:
        yield


@pytest.hookimpl(tryfirst=True)
def pytest_sessionfinish(session: Session, exitstatus: ExitCode) -> None:
    if session.config.getoption("--enable-orisa") and not session.config.getoption(
        "--collect-only"
    ):
        REPORT.total_duration = (
            time.time()
            - session.config.pluginmanager.get_plugin(
                "terminalreporter"
            )._sessionstarttime
        )
        REPORT.exit_status = exitstatus
        send_event(
            Event(
                type=EventType.REPORT,
                data=asdict(REPORT),
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


def pytest_addoption(parser):
    parser.addoption(
        "--enable-orisa",
        action="store_true",
        default=False,
        help="Enable Orisa plugin functionality",
    )


@pytest.hookimpl(trylast=True)
def pytest_configure(config: Config) -> None:
    run_log_width = os.getenv("ORISA_RUN_LOG_WIDTH")
    if run_log_width is not None:
        run_log_width = int(run_log_width)

        terminal_writer: TerminalWriter = config.get_terminal_writer()
        terminal_writer.fullwidth = run_log_width


def pytest_collection_modifyitems(
    session: Session, config: Config, items: list[nodes.Item]
) -> None:
    if config.getoption("--enable-orisa"):
        if config.getoption("--collect-only"):
            send_event(
                Event(
                    type=EventType.TREE_COLLECTION,
                    data=build_pytest_tree(items),
                )
            )


def pytest_collection_finish(session: Session) -> None:
    if session.config.getoption("--enable-orisa") and not session.config.getoption(
        "--collect-only"
    ):
        send_event(
            Event(
                type=EventType.TESTS_TO_RUN_COLLECTION,
                data=[item.nodeid for item in session.items],
            )
        )


def collect_tests() -> None:
    try:
        subprocess.run(
            ["pytest", "--collect-only", "-q", "--enable-orisa"],
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

        args: list[str] = [path, "--enable-orisa"]
        for flag, is_active in pytest_cli_flags:
            if is_active:
                args.append(flag)

    return subprocess.Popen(
        ["pytest", *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
