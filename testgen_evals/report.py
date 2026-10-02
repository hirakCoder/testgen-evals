"""Aggregate per-story metrics and judge scores into ``summary.json`` and ``report.md``."""

from __future__ import annotations

import json
from pathlib import Path
from statistics import median
from typing import Any

from .metrics.deterministic import SuiteMetrics, aggregate, compute_suite_metrics
from .metrics.judge import DIMENSIONS, summarise_judgments
from .schema import GeneratedSuite, Story, dump_json, load_suites


def pct(x: float | None) -> str:
    return "n/a" if x is None else f"{100 * x:.1f}%"


def build_summary(
    stories: dict[str, Story],
    suites: list[GeneratedSuite],
    judge_run: dict[str, Any] | None,
    meta: dict[str, Any],
) -> dict[str, Any]:
    """Compute every number the report needs. ``meta`` holds run provenance (provider, date...)."""
    per_story: list[SuiteMetrics] = [
        compute_suite_metrics(stories[s.story_id], s) for s in suites if s.story_id in stories
    ]
    latencies = [s.latency_ms for s in suites if s.latency_ms]
    tokens_in = [s.input_tokens for s in suites if s.input_tokens is not None]
    tokens_out = [s.output_tokens for s in suites if s.output_tokens is not None]
    costs = [s.cost_usd for s in suites if s.cost_usd is not None]
    generation = {
        "median_latency_ms": round(median(latencies)) if latencies else None,
        "max_latency_ms": round(max(latencies)) if latencies else None,
        "retries": sum(1 for s in suites if s.attempts > 1),
        "input_tokens": sum(tokens_in) if tokens_in else None,
        "output_tokens": sum(tokens_out) if tokens_out else None,
        "cost_usd": round(sum(costs), 4) if costs else None,
        "models": sorted({s.model for s in suites if s.model}),
    }
    summary: dict[str, Any] = {
        "meta": meta,
        "generation": generation,
        "overall": aggregate(per_story),
        "per_story": [m.to_dict() for m in per_story],
    }
    if judge_run is not None:
        judge = summarise_judgments(judge_run)
        judge_costs = [
            j["cost_usd"]
            for j in judge_run.get("judgments", []) + judge_run.get("bias_check", [])
            if j.get("cost_usd") is not None
        ]
        judge["cost_usd"] = round(sum(judge_costs), 4) if judge_costs else None
        summary["judge"] = judge
    return summary


def _table(headers: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(out)


def render_markdown(summary: dict[str, Any], stories: dict[str, Story]) -> str:
    """Render the human-readable report."""
    meta, gen, ov = summary["meta"], summary["generation"], summary["overall"]
    judge = summary.get("judge")
    lines = [
        f"# testgen-evals report - {meta.get('run_id', '')}",
        "",
        f"- Date: {meta.get('date', '')}",
        f"- Generator: `{meta.get('provider', '')}` / `{', '.join(gen['models'])}`",
        f"- Stories file: `{meta.get('stories', '')}`",
        f"- Generation retries: {gen['retries']}; median latency "
        f"{gen['median_latency_ms']} ms; max {gen['max_latency_ms']} ms",
        f"- Tokens: {gen['input_tokens']} in / {gen['output_tokens']} out; "
        f"reported cost: {gen['cost_usd']} USD",
        "",
        "## Overall",
        "",
        _table(
            ["Metric", "Value"],
            [
                ["Stories", f"{ov['stories']} ({ov['stories_parse_ok']} parsed OK)"],
                ["Cases generated", f"{ov['cases_produced']} ({ov['cases_valid']} schema-valid)"],
                ["Schema-valid rate", pct(ov["schema_valid_rate"])],
                [
                    "AC coverage (explicit + fuzzy)",
                    f"{pct(ov['ac_coverage'])} ({ov['ac_covered']}/{ov['ac_total']})",
                ],
                ["AC coverage (explicit `covers` only)", pct(ov["ac_coverage_explicit"])],
                [
                    "Stories with every AC covered",
                    f"{ov['stories_with_full_coverage']}/{ov['stories']}",
                ],
                ["Near-duplicate rate", f"{pct(ov['duplicate_rate'])} ({ov['duplicate_cases']})"],
                [
                    "Case types",
                    ", ".join(f"{k} {v}" for k, v in ov["type_counts"].items()),
                ],
                ["Negative-test ratio", pct(ov["negative_ratio"])],
                ["Edge-test ratio", pct(ov["edge_ratio"])],
                [
                    "Mean steps per case",
                    f"{ov['mean_steps']:.1f} ({ov['cases_over_max_steps']} over the max)",
                ],
                [
                    "Untestable steps",
                    f"{pct(ov['untestable_step_rate'])} "
                    f"({ov['untestable_steps']}/{ov['total_steps']})",
                ],
            ],
        ),
        "",
        "## Per story",
        "",
    ]
    rows = []
    for m in summary["per_story"]:
        title = stories[m["story_id"]].title if m["story_id"] in stories else ""
        rows.append(
            [
                f"{m['story_id']} {title}",
                f"{m['cases_valid']}/{m['cases_produced']}",
                f"{m['ac_covered_explicit'] + m['ac_covered_fuzzy']}/{m['ac_total']}"
                + (f" (missing {', '.join(m['uncovered_acs'])})" if m["uncovered_acs"] else ""),
                str(len({b for _, b, _ in m["duplicate_pairs"]})),
                f"{m['type_counts']['negative']}/{m['type_counts']['edge']}",
                f"{m['untestable_steps']}/{m['total_steps']}",
            ]
        )
    lines.append(
        _table(["Story", "Valid/produced", "ACs covered", "Dups", "Neg/edge", "Untestable"], rows)
    )
    if judge:
        lines += ["", "## LLM-as-judge", ""]
        scope = (
            f"{judge['judged']} of {judge['total_cases']} cases (sampled round-robin per story)"
            if judge["sampled"]
            else f"all {judge['judged']} cases"
        )
        lines += [
            f"- Judge model: `{judge['model']}`; scored {scope}; "
            f"{judge['parse_ok']} replies parsed; reported cost {judge['cost_usd']} USD",
            f"- Overall mean: {judge['overall_mean']} / 5",
            "",
            _table(
                ["Dimension", "Mean (1-5)"],
                [[d, str(judge["mean_scores"].get(d, "n/a"))] for d in DIMENSIONS],
            ),
            "",
            "### Per story (mean)",
            "",
            _table(
                ["Story", *DIMENSIONS],
                [[sid, *(str(v[d]) for d in DIMENSIONS)] for sid, v in judge["per_story"].items()],
            ),
            "",
            "### Position-bias check",
            "",
            f"{judge['position_bias']['pairs']} cases were re-judged with the test case placed "
            "before the story. Delta = swapped score - original score.",
            "",
            _table(
                ["Dimension", "Mean signed delta", "Mean abs delta"],
                [
                    [
                        d,
                        str(judge["position_bias"]["mean_signed_delta"][d]),
                        str(judge["position_bias"]["mean_abs_delta"][d]),
                    ]
                    for d in DIMENSIONS
                ],
            ),
            "",
            f"Pairs where at least one score changed: "
            f"{judge['position_bias']['pairs_with_any_change']}/{judge['position_bias']['pairs']}",
        ]
    lines.append("")
    return "\n".join(lines)


def write_report(run_dir: Path, stories: dict[str, Story], meta: dict[str, Any]) -> dict[str, Any]:
    """Read ``suites.json`` (and ``judgments.json`` if present) and write summary + report."""
    suites = load_suites(run_dir / "suites.json")
    judge_path = run_dir / "judgments.json"
    judge_run = json.loads(judge_path.read_text(encoding="utf-8")) if judge_path.exists() else None
    summary = build_summary(stories, suites, judge_run, meta)
    dump_json(summary, run_dir / "summary.json")
    (run_dir / "report.md").write_text(render_markdown(summary, stories), encoding="utf-8")
    return summary
