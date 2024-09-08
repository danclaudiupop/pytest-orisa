import logging
import os
import subprocess
import time
from typing import Generator

import pytest
from _pytest import nodes
from _pytest._io import TerminalWriter
from _pytest.nodes import Node
from pytest import (
    CallInfo,
    Class,
    Config,
    ExitCode,
    Function,
    Item,
    Session,
    TestReport,
)

from pytest_orisa.event_dispatcher import send_event

logging.basicConfig(level=logging.ERROR)
logger: logging.Logger = logging.getLogger(__name__)


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


def pytest_collection_modifyitems(
    session: Session, config: Config, items: list[nodes.Item]
) -> None:
    if config.getoption("--collect-only"):
        send_event(
            event={"type": "tests_collected", "data": build_pytest_tree(session.items)}
        )


REPORT = {
    "passed": [],
    "failed": [],
    "skipped": [],
    "xfailed": [],
    "meta": {"total": 0},
    "setup_durations": {},
    "teardown_durations": {},
}


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: Item, call: CallInfo):
    outcome = yield
    report: TestReport = outcome.get_result()

    def add_report(data, report: TestReport, status: str):
        report_data = {
            "nodeid": report.nodeid,
            "duration": report.duration,
        }
        if status == "passed":
            report_data.update(
                {
                    "fixtures_used": [
                        {
                            "module": "placeholder",
                            "argname": argname,
                            "scope": fixture[0].scope,
                            "location": "placeholder",
                            "lineno": "placeholder",
                        }
                        for argname, fixture in item._fixtureinfo.name2fixturedefs.items()
                    ],
                    "longreprtext": report.longreprtext,
                    "caplog": report.caplog,
                }
            )

        if status == "failed":
            report_data.update(
                {
                    "longreprtext": report.longreprtext,
                    "capstderr": report.capstderr,
                    "caplog": report.caplog,
                }
            )
        data[status].append(report_data)
        data["meta"]["total"] += 1

    if report.when == "call":
        if report.passed:
            add_report(REPORT, report, "passed")
        elif report.failed:
            add_report(REPORT, report, "failed")
        elif report.skipped:
            add_report(REPORT, report, "skipped")
        elif report.xfailed:
            add_report(REPORT, report, "xfailed")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_setup(item: Item) -> Generator:
    nodeid = item.nodeid
    start_time = time.time()
    yield
    end_time = time.time()
    REPORT["setup_durations"][nodeid] = end_time - start_time


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_teardown(item: Item) -> Generator:
    nodeid = item.nodeid
    start_time = time.time()
    yield
    end_time = time.time()
    REPORT["teardown_durations"][nodeid] = end_time - start_time


@pytest.hookimpl(trylast=True)
def pytest_configure(config: Config) -> None:
    run_log_width = os.getenv("ORISA_RUN_LOG_WIDTH")
    if run_log_width is not None:
        run_log_width = int(run_log_width)

        terminal_writer: TerminalWriter = config.get_terminal_writer()
        terminal_writer.fullwidth = run_log_width


@pytest.hookimpl(tryfirst=True)
def pytest_sessionfinish(session: Session, exitstatus: ExitCode) -> None:
    if not session.config.getoption("--collect-only"):
        REPORT["meta"]["total_duration"] = (
            time.time()
            - session.config.pluginmanager.get_plugin(
                "terminalreporter"
            )._sessionstarttime
        )
        REPORT["meta"]["exit_status"] = exitstatus
        send_event(event={"type": "report", "data": REPORT})


def collect_tests() -> None:
    try:
        subprocess.run(["pytest", "--collect-only"], check=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"pytest collection failed: {e}") from e
    except Exception as e:
        raise RuntimeError(f"An unexpected error occurred: {str(e)}") from e


def run_node(
    node: dict | None, pytest_cli_flags: list[tuple[str, bool]]
) -> subprocess.Popen[str]:
    if node is not None:
        if node["type"] == "FUNCTION" and node["parent_type"] == "CLASS":
            path = f"{node['path']}::{node['parent_name']}::{node['name']}"
        elif node["type"] in ["CLASS", "FUNCTION"]:
            path = f"{node['path']}::{node['name']}"
        else:
            path = node["path"]

        args: list[str] = [path]
        for flag, is_active in pytest_cli_flags:
            if is_active:
                args.append(flag)

    return subprocess.Popen(
        ["pytest", *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
