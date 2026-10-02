import json

import pytest

from testgen_evals.generate import extract_json, generate_suite
from testgen_evals.providers import FakeProvider

VALID = json.dumps(
    {
        "test_cases": [
            {
                "id": "TC-1",
                "title": "Valid code reduces subtotal",
                "type": "positive",
                "covers": ["AC-1"],
                "preconditions": ["Cart subtotal is 50.00"],
                "steps": [{"action": "Apply SAVE10", "expected": "Subtotal shows 45.00"}],
            }
        ]
    }
)


def test_extract_json_handles_fences_and_prose():
    assert extract_json('Sure:\n```json\n{"a": 1}\n```\nDone.') == {"a": 1}
    assert extract_json('prefix {"a": [1, 2]} suffix') == {"a": [1, 2]}
    assert extract_json("[1, 2]") == [1, 2]
    with pytest.raises(ValueError):
        extract_json("no json here")
    with pytest.raises(ValueError):
        extract_json("{broken: json")


def test_generate_suite_parses_first_attempt(stories):
    provider = FakeProvider([VALID])
    suite = generate_suite(provider, stories["ST-001"], system="sys")
    assert suite.parse_ok and suite.attempts == 1
    assert [c.id for c in suite.cases] == ["TC-1"]
    assert provider.calls[0][1] == "sys"
    assert "ST-001" in provider.calls[0][0]


def test_generate_suite_retries_once_on_bad_json(stories):
    provider = FakeProvider(["I cannot answer that.", VALID])
    suite = generate_suite(provider, stories["ST-001"], system="sys")
    assert suite.parse_ok and suite.attempts == 2
    assert len(provider.calls) == 2
    assert "not valid JSON" in provider.calls[1][0]
    assert suite.schema_errors[0].startswith("attempt 1:")


def test_generate_suite_gives_up_after_second_failure(stories):
    provider = FakeProvider(["nope", "still nope"])
    suite = generate_suite(provider, stories["ST-001"], system="sys")
    assert not suite.parse_ok and suite.attempts == 2 and suite.cases == []


def test_generate_suite_keeps_invalid_cases_for_schema_rate(stories, tmp_path):
    payload = {"test_cases": [json.loads(VALID)["test_cases"][0], {"id": "TC-2"}]}
    provider = FakeProvider([json.dumps(payload)])
    suite = generate_suite(provider, stories["ST-001"], system="sys", raw_dir=tmp_path)
    assert len(suite.cases) == 1 and len(suite.invalid_cases) == 1
    assert (tmp_path / "ST-001.attempt1.txt").exists()
