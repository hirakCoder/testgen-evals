from conftest import load_golden_raw

from testgen_evals.schema import Step, TestCase, parse_suite_payload, validate_case


def test_dataset_stories_are_well_formed(stories):
    assert 8 <= len(stories) <= 12
    for s in stories.values():
        assert 3 <= len(s.acceptance_criteria) <= 6
        assert s.ac_ids == [f"AC-{i}" for i in range(1, len(s.acceptance_criteria) + 1)]


def test_validate_case_reports_each_violation():
    assert validate_case("not a dict") == ["case[0]: not an object"]
    errs = validate_case({"id": "", "title": "t", "type": "smoke", "steps": []}, 2)
    assert any("'id'" in e for e in errs)
    assert any("'type'" in e for e in errs)
    assert any("'steps'" in e for e in errs)
    assert all(e.startswith("case[2]") for e in errs)


def test_parse_suite_payload_splits_valid_and_invalid():
    payload = load_golden_raw("ST-001_invalid_schema.json")
    valid, invalid, errors = parse_suite_payload(payload)
    assert [c.id for c in valid] == ["TC-1", "TC-2", "TC-5"]
    assert len(invalid) == 3
    assert any("'type' must be one of" in e for e in errors)
    assert any("missing 'steps'" in e for e in errors)
    assert any("duplicate id 'TC-5'" in e for e in errors)


def test_parse_suite_payload_rejects_non_list():
    assert parse_suite_payload({"foo": "bar"}) == ([], [], ["payload is not a list of test cases"])


def test_test_case_round_trip():
    tc = TestCase("TC-1", "t", "positive", ("AC-1",), ("logged in",), (Step("do", "see"),))
    assert TestCase.from_dict(tc.to_dict()) == tc
    assert "logged in" in tc.text() and "see" in tc.text()
