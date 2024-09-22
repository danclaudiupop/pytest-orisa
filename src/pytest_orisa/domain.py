from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum


class NodeType(str, Enum):
    DIR = "DIR"
    MODULE = "MODULE"
    CLASS = "CLASS"
    FUNCTION = "FUNCTION"


class EventType(str, Enum):
    TREE_COLLECTION = "TREE_COLLECTION"
    TESTS_TO_RUN_COLLECTION = "TESTS_TO_RUN_COLLECTION"
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
