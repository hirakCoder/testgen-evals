"""Data model for stories, generated test cases, and their JSON (de)serialisation.

Everything here is plain dataclasses plus hand-written validation. The validation
is deliberately strict: a generated test case that does not meet the contract is
counted as *invalid*, which is itself one of the metrics we report.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

CASE_TYPES = ("positive", "negative", "edge")
MAX_STEPS = 12


@dataclass(frozen=True)
class AcceptanceCriterion:
    id: str
    text: str


@dataclass(frozen=True)
class Story:
    id: str
    title: str
    domain: str
    story: str
    acceptance_criteria: tuple[AcceptanceCriterion, ...]

    @property
    def ac_ids(self) -> list[str]:
        return [ac.id for ac in self.acceptance_criteria]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "domain": self.domain,
            "story": self.story,
            "acceptance_criteria": [asdict(ac) for ac in self.acceptance_criteria],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Story:
        acs = tuple(AcceptanceCriterion(ac["id"], ac["text"]) for ac in d["acceptance_criteria"])
        return cls(d["id"], d["title"], d.get("domain", ""), d["story"], acs)


@dataclass(frozen=True)
class Step:
    action: str
    expected: str


@dataclass(frozen=True)
class TestCase:
    id: str
    title: str
    type: str
    covers: tuple[str, ...]
    preconditions: tuple[str, ...]
    steps: tuple[Step, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "type": self.type,
            "covers": list(self.covers),
            "preconditions": list(self.preconditions),
            "steps": [asdict(s) for s in self.steps],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TestCase:
        return cls(
            id=str(d["id"]),
            title=str(d["title"]),
            type=str(d["type"]),
            covers=tuple(str(c) for c in d.get("covers", [])),
            preconditions=tuple(str(p) for p in d.get("preconditions", [])),
            steps=tuple(Step(str(s["action"]), str(s.get("expected", ""))) for s in d["steps"]),
        )

    def text(self) -> str:
        """Flattened text used by similarity and fuzzy-coverage metrics."""
        parts = [self.title, *self.preconditions]
        for s in self.steps:
            parts.extend([s.action, s.expected])
        return " ".join(parts)


@dataclass
class GeneratedSuite:
    """One generator response for one story, plus everything we know about the call."""

    story_id: str
    cases: list[TestCase] = field(default_factory=list)
    invalid_cases: list[dict[str, Any]] = field(default_factory=list)
    schema_errors: list[str] = field(default_factory=list)
    parse_ok: bool = True
    attempts: int = 1
    latency_ms: float = 0.0
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    model: str = ""
    provider: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["cases"] = [c.to_dict() for c in self.cases]
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> GeneratedSuite:
        d = dict(d)
        d["cases"] = [TestCase.from_dict(c) for c in d.get("cases", [])]
        return cls(**d)


def validate_case(obj: Any, index: int = 0) -> list[str]:
    """Return a list of schema violations for one raw test-case object. Empty means valid."""
    where = f"case[{index}]"
    if not isinstance(obj, dict):
        return [f"{where}: not an object"]
    errors: list[str] = []
    for key in ("id", "title", "type", "steps"):
        if key not in obj:
            errors.append(f"{where}: missing '{key}'")
    if errors:
        return errors
    if not isinstance(obj["id"], str) or not obj["id"].strip():
        errors.append(f"{where}: 'id' must be a non-empty string")
    if not isinstance(obj["title"], str) or not obj["title"].strip():
        errors.append(f"{where}: 'title' must be a non-empty string")
    if obj["type"] not in CASE_TYPES:
        errors.append(f"{where}: 'type' must be one of {CASE_TYPES}, got {obj['type']!r}")
    covers = obj.get("covers", [])
    if not isinstance(covers, list) or not all(isinstance(c, str) for c in covers):
        errors.append(f"{where}: 'covers' must be a list of strings")
    pre = obj.get("preconditions", [])
    if not isinstance(pre, list) or not all(isinstance(p, str) for p in pre):
        errors.append(f"{where}: 'preconditions' must be a list of strings")
    steps = obj["steps"]
    if not isinstance(steps, list) or not steps:
        errors.append(f"{where}: 'steps' must be a non-empty list")
        return errors
    for i, s in enumerate(steps):
        action = s.get("action") if isinstance(s, dict) else None
        if not isinstance(action, str) or not action.strip():
            errors.append(f"{where}.steps[{i}]: 'action' must be a non-empty string")
        if "expected" in s and not isinstance(s["expected"], str):
            errors.append(f"{where}.steps[{i}]: 'expected' must be a string")
    return errors


def parse_suite_payload(payload: Any) -> tuple[list[TestCase], list[dict[str, Any]], list[str]]:
    """Split a raw generator payload into (valid cases, invalid raw objects, error messages).

    Accepts either a bare list or ``{"test_cases": [...]}``.
    """
    if isinstance(payload, dict):
        payload = payload.get("test_cases", payload.get("cases"))
    if not isinstance(payload, list):
        return [], [], ["payload is not a list of test cases"]
    valid: list[TestCase] = []
    invalid: list[dict[str, Any]] = []
    errors: list[str] = []
    seen_ids: set[str] = set()
    for i, obj in enumerate(payload):
        errs = validate_case(obj, i)
        if not errs and obj["id"] in seen_ids:
            errs = [f"case[{i}]: duplicate id {obj['id']!r}"]
        if errs:
            errors.extend(errs)
            invalid.append(obj if isinstance(obj, dict) else {"_raw": obj})
            continue
        seen_ids.add(obj["id"])
        valid.append(TestCase.from_dict(obj))
    return valid, invalid, errors


def load_stories(path: str | Path) -> list[Story]:
    """Read a JSONL file of stories (one JSON object per line; blank lines ignored)."""
    stories: list[Story] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                stories.append(Story.from_dict(json.loads(line)))
    return stories


def load_suites(path: str | Path) -> list[GeneratedSuite]:
    """Read a suites.json file written by a run."""
    with open(path, encoding="utf-8") as fh:
        return [GeneratedSuite.from_dict(d) for d in json.load(fh)]


def dump_json(obj: Any, path: str | Path) -> None:
    """Write pretty, stable JSON (sorted keys off so field order stays readable)."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
