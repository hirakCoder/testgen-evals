"""Command line entry point.

python -m testgen_evals run    --provider claude-cli --stories datasets/stories.jsonl --out runs/
python -m testgen_evals judge  runs/<run_id> --provider claude-cli --max-calls 60
python -m testgen_evals report runs/<run_id>
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from . import __version__
from .generate import generate_suite
from .metrics.judge import judge_suites
from .providers import get_provider
from .report import write_report
from .schema import dump_json, load_stories, load_suites


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _cli_version() -> str:
    exe = shutil.which("claude")
    if not exe:
        return ""
    try:
        return subprocess.run(
            [exe, "--version"], capture_output=True, text=True, timeout=30
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _read_meta(run_dir: Path) -> dict:
    path = run_dir / "meta.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def cmd_run(args: argparse.Namespace) -> int:
    stories = load_stories(args.stories)
    if args.limit:
        stories = stories[: args.limit]
    provider = get_provider(args.provider, args.model)
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir = Path(args.out) / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    meta = {
        "run_id": run_id,
        "date": datetime.now(UTC).date().isoformat(),
        "provider": provider.name,
        "model": provider.model,
        "stories": str(args.stories),
        "harness_version": __version__,
        "claude_cli_version": _cli_version() if provider.name == "claude-cli" else "",
    }
    dump_json(meta, run_dir / "meta.json")
    _log(f"run {run_id}: {len(stories)} stories via {provider.name}/{provider.model}")
    suites = []
    for i, story in enumerate(stories, 1):
        suite = generate_suite(provider, story, raw_dir=run_dir / "raw")
        suites.append(suite)
        _log(
            f"  [{i}/{len(stories)}] {story.id}: {len(suite.cases)} valid, "
            f"{len(suite.invalid_cases)} invalid, attempts={suite.attempts}, "
            f"{suite.latency_ms:.0f} ms"
        )
    dump_json([s.to_dict() for s in suites], run_dir / "suites.json")
    if args.judge:
        _run_judge(run_dir, provider, args.max_judge_calls, args.bias_check, args.seed)
    write_report(run_dir, {s.id: s for s in stories}, meta)
    _log(f"wrote {run_dir / 'summary.json'} and {run_dir / 'report.md'}")
    return 0


def _run_judge(run_dir: Path, provider, max_calls: int, bias_check: int, seed: int) -> None:
    meta = _read_meta(run_dir)
    stories = {s.id: s for s in load_stories(meta.get("stories", "datasets/stories.jsonl"))}
    suites = load_suites(run_dir / "suites.json")
    _log(f"judging with {provider.name}/{provider.model} (max {max_calls} calls)")
    judge_run = judge_suites(provider, stories, suites, max_calls, bias_check, seed, log=_log)
    dump_json(judge_run, run_dir / "judgments.json")


def cmd_judge(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir)
    provider = get_provider(args.provider, args.model)
    _run_judge(run_dir, provider, args.max_calls, args.bias_check, args.seed)
    return cmd_report(args)


def cmd_report(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir)
    meta = _read_meta(run_dir)
    stories = {s.id: s for s in load_stories(meta.get("stories", "datasets/stories.jsonl"))}
    summary = write_report(run_dir, stories, meta)
    ov = summary["overall"]
    _log(
        f"{run_dir.name}: {ov['cases_valid']}/{ov['cases_produced']} valid cases, "
        f"AC coverage {100 * ov['ac_coverage']:.0f}%, duplicates {100 * ov['duplicate_rate']:.0f}%"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="testgen-evals", description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="command", required=True)

    def add_provider(sp: argparse.ArgumentParser) -> None:
        sp.add_argument(
            "--provider", default="claude-cli", choices=["claude-cli", "anthropic", "openai"]
        )
        sp.add_argument("--model", default=None, help="override the provider's default model")

    def add_judge_opts(sp: argparse.ArgumentParser, flag: str) -> None:
        sp.add_argument(flag, type=int, default=60, help="cap on judge calls incl. bias check")
        sp.add_argument("--bias-check", type=int, default=8, help="cases re-judged case-first")
        sp.add_argument("--seed", type=int, default=0)

    run = sub.add_parser("run", help="generate suites, score them, write a report")
    add_provider(run)
    run.add_argument("--stories", default="datasets/stories.jsonl")
    run.add_argument("--out", default="runs")
    run.add_argument("--limit", type=int, default=0, help="only the first N stories")
    run.add_argument("--judge", action="store_true", help="also run the LLM judge")
    add_judge_opts(run, "--max-judge-calls")
    run.set_defaults(func=cmd_run)

    judge = sub.add_parser("judge", help="run the LLM judge over an existing run")
    judge.add_argument("run_dir")
    add_provider(judge)
    add_judge_opts(judge, "--max-calls")
    judge.set_defaults(func=cmd_judge)

    report = sub.add_parser("report", help="rebuild summary.json and report.md for a run")
    report.add_argument("run_dir")
    report.set_defaults(func=cmd_report)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
