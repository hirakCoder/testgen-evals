from conftest import load_golden, load_golden_raw

from testgen_evals.metrics.deterministic import (
    ac_coverage,
    aggregate,
    compute_suite_metrics,
    find_duplicates,
    is_untestable,
    jaccard,
    tokens,
)
from testgen_evals.schema import GeneratedSuite, Step, parse_suite_payload


def test_tokens_and_jaccard():
    assert tokens("The user clicks the Save button.") == {"save", "button"}
    assert jaccard(set(), set()) == 0.0
    assert jaccard({"a", "b"}, {"a", "b"}) == 1.0
    assert jaccard({"a", "b"}, {"b", "c"}) == 1 / 3


def test_coverage_gaps_golden(stories):
    suite = load_golden("ST-004_coverage_gaps.json")
    cov = ac_coverage(stories["ST-004"], suite.cases)
    assert cov.covered_explicit == ["AC-1", "AC-3", "AC-4"]
    assert cov.covered_fuzzy == ["AC-5"]  # TC-4 restates AC-5 but has no `covers` tag
    assert cov.uncovered == ["AC-2", "AC-6"]
    assert cov.unknown_refs == ["AC-9"]

    m = compute_suite_metrics(stories["ST-004"], suite)
    assert m.ac_total == 6
    assert m.ac_coverage_explicit == 3 / 6
    assert m.ac_coverage == 4 / 6
    assert m.duplicate_pairs == []
    assert m.untestable_steps == 0
    assert m.negative_ratio == 2 / 4


def test_duplicates_and_untestable_steps_golden(stories):
    suite = load_golden("ST-007_duplicates.json")
    pairs = find_duplicates(suite.cases)
    assert [(a, b) for a, b, _ in pairs] == [("TC-1", "TC-2")]
    assert pairs[0][2] >= 0.8

    m = compute_suite_metrics(stories["ST-007"], suite)
    assert m.cases_valid == 5
    assert m.duplicate_rate == 1 / 5
    assert m.untestable_steps == 2  # "works as expected" and an empty expected result
    assert m.total_steps == 7
    assert m.untestable_step_rate == 2 / 7
    assert m.uncovered_acs == []
    assert m.type_counts == {"positive": 2, "negative": 2, "edge": 1}


def test_is_untestable_heuristics():
    assert is_untestable(Step("click", ""))
    assert is_untestable(Step("click", "Works as expected."))
    assert is_untestable(Step("click", "It works"))
    assert is_untestable(Step("click", "OK"))
    assert not is_untestable(Step("click", "The order total shows 45.00 and the code is listed"))


def test_schema_validity_counts_invalid_cases(stories):
    valid, invalid, errors = parse_suite_payload(load_golden_raw("ST-001_invalid_schema.json"))
    suite = GeneratedSuite("ST-001", cases=valid, invalid_cases=invalid, schema_errors=errors)
    m = compute_suite_metrics(stories["ST-001"], suite)
    assert m.cases_produced == 6
    assert m.cases_valid == 3
    assert m.schema_valid_rate == 0.5
    # the invalid cases' `covers` do not count towards coverage
    assert m.uncovered_acs == ["AC-3", "AC-4"]


def test_aggregate_is_case_weighted(stories):
    a = compute_suite_metrics(stories["ST-004"], load_golden("ST-004_coverage_gaps.json"))
    b = compute_suite_metrics(stories["ST-007"], load_golden("ST-007_duplicates.json"))
    agg = aggregate([a, b])
    assert agg["stories"] == 2
    assert agg["cases_valid"] == 9
    assert agg["ac_total"] == 10
    assert agg["ac_covered"] == 8
    assert agg["duplicate_cases"] == 1
    assert agg["duplicate_rate"] == 1 / 9
    assert agg["untestable_step_rate"] == 2 / 13
    assert agg["stories_with_full_coverage"] == 1


def test_empty_suite_yields_zero_rates(stories):
    m = compute_suite_metrics(stories["ST-001"], GeneratedSuite("ST-001", parse_ok=False))
    assert m.cases_valid == 0 and m.ac_coverage == 0.0 and m.duplicate_rate == 0.0
    assert aggregate([m])["schema_valid_rate"] == 0.0
