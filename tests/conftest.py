import json
from pathlib import Path

import pytest

from testgen_evals.schema import GeneratedSuite, Story, load_stories

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "datasets" / "golden"


@pytest.fixture(scope="session")
def stories() -> dict[str, Story]:
    return {s.id: s for s in load_stories(ROOT / "datasets" / "stories.jsonl")}


def load_golden(name: str) -> GeneratedSuite:
    with open(GOLDEN / name, encoding="utf-8") as fh:
        return GeneratedSuite.from_dict(json.load(fh))


def load_golden_raw(name: str) -> dict:
    with open(GOLDEN / name, encoding="utf-8") as fh:
        return json.load(fh)
