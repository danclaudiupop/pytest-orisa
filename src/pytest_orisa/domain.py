from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class NodeType(str, Enum):
    DIR = "DIR"
    MODULE = "MODULE"
    CLASS = "CLASS"
    FUNCTION = "FUNCTION"


class EventType(str, Enum):
    TESTS_COLLECTED = "TESTS_COLLECTED"
    TESTS_SCHEDULED = "TESTS_SCHEDULED"
    TEST_OUTCOME = "TEST_OUTCOME"
    REPORT = "REPORT"


@dataclass(frozen=True)
class Event:
    type: EventType
    data: dict | list

    def serialize(self) -> str:
        return json.dumps(
            {
                "type": self.type,
                "data": self.data,
            }
        )

    @classmethod
    def deserialize(cls, json_str: str) -> Event:
        parsed = json.loads(json_str)
        return cls(type=EventType(parsed["type"]), data=parsed["data"])


@dataclass
class TestItem:
    nodeid: str
    call_duration: float = 0.0
    status: str = "running"
    skip_reason: str = ""
    fixtures: list[dict[str, Any]] = field(default_factory=list)
    caplog: str = ""
    longreprtext: str = ""
    capstderr: str = ""


@dataclass
class Report:
    passed: list[TestItem] = field(default_factory=list)
    failed: list[TestItem] = field(default_factory=list)
    skipped: list[TestItem] = field(default_factory=list)
    xfailed: list[TestItem] = field(default_factory=list)
    setup_durations: dict[str, float] = field(default_factory=dict)
    teardown_durations: dict[str, float] = field(default_factory=dict)
    total_duration: float = 0.0
    exit_status: int = 0

    def get_test_item_by_nodeid(self, nodeid: str) -> TestItem | None:
        for test_list in [self.passed, self.failed, self.skipped, self.xfailed]:
            for test_item in test_list:
                if test_item.nodeid == nodeid:
                    return test_item
        return None
