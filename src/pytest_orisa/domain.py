from dataclasses import dataclass


@dataclass(frozen=True)
class EventType:
    TREE_COLLECTION: str = "TREE_COLLECTION"
    TESTS_TO_RUN_COLLECTION: str = "TESTS_TO_RUN_COLLECTION"
    TEST_OUTCOME: str = "TEST_OUTCOME"
    REPORT: str = "REPORT"


@dataclass
class Event:
    type: EventType | str
    data: dict | list

    def deserialize(self):
        import json

        return json.dumps({"type": self.type, "data": self.data})
