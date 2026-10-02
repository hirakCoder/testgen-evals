import json

from conftest import GOLDEN

from testgen_evals.cli import main
from testgen_evals.report import build_summary, render_markdown
from testgen_evals.schema import GeneratedSuite, dump_json


def _golden_suites():
    out = []
    for name in ("ST-004_coverage_gaps.json", "ST-007_duplicates.json"):
        with open(GOLDEN / name, encoding="utf-8") as fh:
            out.append(GeneratedSuite.from_dict(json.load(fh)))
    return out


def test_build_summary_and_markdown_without_judge(stories):
    summary = build_summary(stories, _golden_suites(), None, {"run_id": "t", "date": "2026-01-01"})
    assert summary["overall"]["cases_valid"] == 9
    assert "judge" not in summary
    md = render_markdown(summary, stories)
    assert "## Overall" in md and "ST-004" in md and "missing AC-2, AC-6" in md
    assert "LLM-as-judge" not in md


def test_report_command_rebuilds_from_run_dir(tmp_path, stories):
    run_dir = tmp_path / "r1"
    dump_json([s.to_dict() for s in _golden_suites()], run_dir / "suites.json")
    dump_json(
        {"run_id": "r1", "date": "2026-01-01", "stories": "datasets/stories.jsonl"},
        run_dir / "meta.json",
    )
    judge_run = {
        "judgments": [
            {
                "story_id": "ST-007",
                "case_id": "TC-1",
                "order": "story_first",
                "scores": {"correctness": 5, "completeness": 4, "clarity": 5, "independence": 5},
                "rationale": "ok",
                "parse_ok": True,
                "latency_ms": 1,
                "cost_usd": 0.01,
                "model": "fake-1",
                "error": "",
            }
        ],
        "bias_check": [],
        "sampled": True,
        "total_cases": 9,
    }
    dump_json(judge_run, run_dir / "judgments.json")
    assert main(["report", str(run_dir)]) == 0
    summary = json.loads((run_dir / "summary.json").read_text())
    assert summary["judge"]["mean_scores"]["completeness"] == 4.0
    assert summary["judge"]["cost_usd"] == 0.01
    md = (run_dir / "report.md").read_text()
    assert "## LLM-as-judge" in md and "1 of 9 cases" in md
