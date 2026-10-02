import json

from conftest import load_golden

from testgen_evals.metrics.judge import (
    build_judge_prompt,
    judge_case,
    judge_suites,
    parse_judgment,
    select_cases,
    summarise_judgments,
)
from testgen_evals.providers import FakeProvider


def reply(c=4, co=3, cl=5, i=4, why="fine"):
    return json.dumps(
        {"correctness": c, "completeness": co, "clarity": cl, "independence": i, "rationale": why}
    )


def test_parse_judgment_validates_range():
    scores, why = parse_judgment(reply())
    assert scores == {"correctness": 4, "completeness": 3, "clarity": 5, "independence": 4}
    assert why == "fine"
    for bad in ('{"correctness": 6}', '{"correctness": "4"}', "[1]"):
        try:
            parse_judgment(bad)
        except ValueError:
            continue
        raise AssertionError(f"expected ValueError for {bad}")


def test_prompt_order_is_swappable(stories):
    suite = load_golden("ST-007_duplicates.json")
    story, case = stories["ST-007"], suite.cases[0]
    a = build_judge_prompt(story, case, "story_first")
    b = build_judge_prompt(story, case, "case_first")
    assert a.index("USER STORY") < a.index("TEST CASE")
    assert b.index("TEST CASE") < b.index("USER STORY")


def test_judge_case_records_order_and_handles_bad_reply(stories):
    suite = load_golden("ST-007_duplicates.json")
    good = judge_case(FakeProvider([reply()]), stories["ST-007"], suite.cases[0], system="s")
    assert good.parse_ok and good.order == "story_first" and good.scores["clarity"] == 5
    bad = judge_case(FakeProvider(["no json"]), stories["ST-007"], suite.cases[0], system="s")
    assert not bad.parse_ok and bad.error


def test_select_cases_round_robins_across_stories(stories):
    suites = [load_golden("ST-004_coverage_gaps.json"), load_golden("ST-007_duplicates.json")]
    picked = select_cases(stories, suites, max_cases=4)
    assert [s.id for s, _ in picked] == ["ST-004", "ST-007", "ST-004", "ST-007"]
    assert len(select_cases(stories, suites, max_cases=100)) == 9


def test_judge_suites_and_bias_summary(stories, monkeypatch):
    monkeypatch.setattr("testgen_evals.metrics.judge.load_prompt", lambda name: "sys")
    suites = [load_golden("ST-004_coverage_gaps.json"), load_golden("ST-007_duplicates.json")]

    def respond(prompt: str, system: str) -> str:
        # the swapped order scores clarity one point lower, so the bias check must see a delta
        return reply(cl=4) if prompt.startswith("TEST CASE") else reply(cl=5)

    run = judge_suites(FakeProvider(respond), stories, suites, max_calls=6, bias_check=2)
    assert len(run["judgments"]) == 4 and len(run["bias_check"]) == 2
    assert run["sampled"] is True and run["total_cases"] == 9
    summary = summarise_judgments(run)
    assert summary["judged"] == 4 and summary["parse_ok"] == 4
    assert summary["mean_scores"]["clarity"] == 5.0
    assert summary["overall_mean"] == 4.0
    assert summary["position_bias"]["pairs"] == 2
    assert summary["position_bias"]["mean_signed_delta"]["clarity"] == -1.0
    assert summary["position_bias"]["mean_abs_delta"]["correctness"] == 0.0
    assert summary["position_bias"]["pairs_with_any_change"] == 2
    assert set(summary["per_story"]) == {"ST-004", "ST-007"}
