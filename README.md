# testgen-evals

**TL;DR from the committed run:** an LLM wrote 71 test cases for 10 user stories. Every acceptance criterion was tagged as covered — 100%, schema-valid, no vague steps. A second model then graded each case and scored **9 of 52 cases 2/5 on completeness**: right criterion, one branch checked. Tag-level coverage is necessary, not sufficient. [Results](#results) · [How it scores](#how-it-scores)


An evaluation harness for LLM-generated test cases.

Give it user stories with acceptance criteria. An LLM writes structured test cases for each
story. The harness then scores the output two ways: deterministic metrics that need no model,
and an LLM-as-judge rubric with a built-in position-bias check. It writes a JSON summary and a
Markdown report per run.

## Why evaluate generated test cases

Test generation is the easiest place to be fooled by an LLM. The output looks like a test
suite, so people treat it as one. Three things go wrong quietly:

- **Coverage illusion.** Every acceptance criterion gets a test with the right tag, but the
  test checks one branch of a three-branch criterion. Tag-level coverage reads 100%.
- **Duplicates.** The same scenario reappears under a different title, inflating the count.
- **Untestable steps.** "Expected: works correctly." Nothing a tester can observe.

Shipping the suite without measuring this moves the risk, it does not remove it. This harness
measures it: what the model produced, what the structure says about it, and what a second model
thinks of it. Numbers from a real run are in [Results](#results).

## Quick start

```bash
git clone https://github.com/hirakCoder/testgen-evals && cd testgen-evals
python -m pip install -e ".[dev]" && pytest                 # offline, no keys needed
python -m testgen_evals run --provider claude-cli --judge   # real run, writes runs/<id>/
```

`claude-cli` shells out to the [Claude Code](https://docs.claude.com/en/docs/claude-code) CLI
already logged in on your machine. `--provider anthropic` uses the SDK with `ANTHROPIC_API_KEY`;
`--provider openai` uses `OPENAI_API_KEY`. `--model` overrides the default for any provider.

Other commands:

```bash
python -m testgen_evals judge runs/<id> --provider claude-cli --model opus --max-calls 60
python -m testgen_evals report runs/<id>      # rebuild summary.json + report.md
```

## How it scores

| Metric | What it catches | Type |
|---|---|---|
| Schema-valid rate | Replies that are not JSON, cases missing fields, bad `type`, empty `steps`, duplicate ids. One retry on unparseable JSON, then counted as failed. | deterministic |
| AC coverage | Acceptance criteria not referenced by any valid case. Explicit `covers` ids first; a fuzzy fallback (>= 50% of the criterion's content tokens appear in one case) rescues untagged cases and is reported separately. | deterministic |
| Near-duplicate rate | Cases whose normalised token set has Jaccard >= 0.8 with an earlier case. | deterministic |
| Negative / edge ratio | Happy-path bias: share of cases typed `negative` and `edge`. | deterministic |
| Step-count sanity | Mean steps per case and cases over 12 steps. | deterministic |
| Untestable steps | Steps whose expected result is empty, a vague phrase ("works as expected", "OK"), or under three content tokens. | deterministic |
| Correctness | Expectations the story does not support, or invented behaviour. | judge, 1-5 |
| Completeness | Cases that tag a criterion but verify only part of it. | judge, 1-5 |
| Clarity | Steps another tester could not execute without guessing. | judge, 1-5 |
| Independence | Hidden dependence on other cases or unstated state. | judge, 1-5 |
| Position-bias check | A sample of cases is re-judged with the story and test case swapped; the per-dimension deltas are reported. | judge diagnostic |

The judge sees the story and one test case per call and returns scores plus a one-sentence
rationale. Rationales are kept in `judgments.json` so low scores can be audited.

## Results

Run `20261002T191317Z`, 2026-10-02. Generator: `claude-sonnet-5` through Claude Code CLI
2.1.281 (`--model sonnet`). Judge: `claude-opus-5-5` through the same CLI (`--model opus`).
Dataset: `datasets/stories.jsonl`, 10 stories across checkout, a reservations API,
ride booking, password reset, file upload, email verification, cart, catalog filtering, 2FA
and returns; 49 acceptance criteria. Full report:
[`runs/20261002T191317Z/report.md`](runs/20261002T191317Z/report.md).

| Metric | Value |
|---|---|
| Stories / cases generated | 10 / 71 (6 to 8 per story) |
| Schema-valid | 100% (71/71), 0 retries |
| AC coverage, explicit `covers` | 100% (49/49); fuzzy fallback never needed |
| Near-duplicate rate | 1.4% (1 pair, see below) |
| Case types | positive 24, negative 29, edge 18 |
| Negative-test ratio | 40.8% (edge 25.4%) |
| Untestable steps | 0% (0/176) |
| Mean steps per case | 2.5 |
| Median generation latency | 15.2 s per story (max 18.4 s) |
| Generation tokens / cost | 20.5k in, 19.1k out, 0.27 USD as reported by the CLI |
| Judge coverage | 52 of 71 cases (round-robin sample, 5 or 6 per story) + 8 re-judged for bias; 60 calls, 1.21 USD |
| Judge mean: correctness | 4.29 |
| Judge mean: completeness | 3.38 |
| Judge mean: clarity | 3.92 |
| Judge mean: independence | 4.44 |
| Position bias, mean abs delta | correctness 0.38, completeness 0.38, clarity 0.25, independence 0.0; 6 of 8 pairs moved on at least one dimension |

### What the numbers say

- **The deterministic layer saturated and the judge did not.** Schema, coverage and
  untestable-step rates all came back perfect, yet the judge gave 2/5 for completeness to 9 of
  52 cases. That gap is the coverage illusion in numbers: a case tagged `AC-5` that checks one
  branch of `AC-5` counts as covered and still earns a 2. Tag-level coverage is necessary, not
  sufficient.
- **Completeness is the weak dimension (3.38), not correctness (4.29).** Typical rationales:
  "skips the 10 MB boundary and the five-file limit", "never actually removes a file",
  "skips the 500-character boundary". The generator writes one clean path per criterion and
  stops.
- **Where correctness dropped, the model invented behaviour.** A 403 for a non-owner
  cancelling a reservation; exact error strings the story never states. These are the cases a
  reviewer must catch, and a deterministic check cannot.
- **No happy-path bias with this prompt.** 41% negative and 25% edge cases. The prompt asks
  for a mix, and the model delivered one. Removing that instruction would be the first ablation.
- **The one duplicate is a false positive.** Token-set Jaccard flagged "filter with only
  minimum price" against "filter with only maximum price" (0.875). They are mirror cases,
  legitimately distinct. The metric needs structure awareness; see roadmap.
- **Judge scores carry about one point of noise.** Swapping section order moved 6 of 8
  re-judged cases by +-1 on some dimension, with no consistent direction. Differences under
  0.5 between two runs of this judge should not be read as signal without more samples.

## Design notes

**Deterministic first.** Every metric that can be computed without a model is, and those run
first. They are free, reproducible and cannot drift. They also tell you when the judge is
worth paying for: if the schema-valid rate is 60%, fix the prompt before scoring quality.

**Judge caveats, stated plainly.**

- *Same-model bias.* A model tends to rate its own style highly. The committed run uses a
  different, stronger model as judge (Opus judging Sonnet). Using one model for both is
  supported but weakens the numbers; the report records both model names so this is visible.
- *Position bias.* Pointwise judges still react to where things sit in the prompt. Every
  judgment records its section order, and `--bias-check N` re-judges N cases with the order
  swapped and reports the deltas. Treat the mean absolute delta as the judge's noise floor.
- *Rubric drift.* The rubric is a versioned file (`prompts/judge.md`) with anchored
  descriptions for 1, 3 and 5. Changing it invalidates comparisons across runs, so the run id
  and date sit at the top of every report.
- *No human calibration yet.* The judge has not been checked against human labels on this
  dataset. Its scores rank cases; they are not yet validated absolute quality.

**Adding a provider.** Subclass `Provider` in `testgen_evals/providers/`, implement
`default_model` and `_call(prompt, system) -> Completion`, and register the name in
`get_provider`. Fill `input_tokens`, `output_tokens` and `cost_usd` when the backend reports
them; the report shows `None` otherwise rather than estimating.

**Adding a dataset.** One JSON object per line in a `.jsonl` file with `id`, `title`,
`domain`, `story` and `acceptance_criteria` as `[{"id": "AC-1", "text": "..."}]`. Pass it with
`--stories`. Hand-written reference suites for tests live in `datasets/golden/` and encode
known defects (coverage gaps, duplicates, invalid schema) so the metrics are tested against
ground truth, not against model output.

**Run artifacts.** `runs/<id>/` holds `meta.json`, `suites.json` (every generated case),
`judgments.json` (scores and rationales), `summary.json` and `report.md`. Raw model replies go
to `raw/`, which is git-ignored.

## Layout

```
testgen_evals/
  schema.py              Story, TestCase, GeneratedSuite; validation; JSON I/O
  generate.py            prompt build, JSON extraction, one retry, token/latency capture
  providers/             claude_cli.py, anthropic_api.py, openai_api.py behind one interface
  metrics/deterministic.py
  metrics/judge.py       rubric judge, sampling, position-bias check
  report.py              summary.json + report.md
  cli.py                 run / judge / report
datasets/stories.jsonl   10 stories, 49 acceptance criteria
datasets/golden/         reference suites with known defects, used by tests
prompts/                 generate.md, judge.md
tests/                   pytest, offline, no LLM
runs/                    committed run summaries and reports
```

## Roadmap

1. Pairwise judge (A vs B, both orders) for comparing two generators or prompts; pointwise
   scores are too noisy for small deltas.
2. A human-labelled calibration set of 50 cases to measure judge agreement (Cohen's kappa) per
   dimension before trusting absolute scores.
3. Structure-aware duplicate detection: compare `covers`, type and per-step action/expected
   pairs instead of one token bag, to stop mirror cases being flagged.
4. Mutation-based test strength: seed small changes into the acceptance criteria and check
   which generated cases would fail, which measures what coverage tags cannot.
5. Prompt ablations run as a matrix (with and without the type-mix instruction, with and
   without `covers`) so prompt changes are measured rather than assumed.

## License

MIT. Copyright 2026 Hirak Banerjee.

---

Built by Hirak Banerjee - Senior Quality Engineer, AI-augmented testing.
[hirakcoder.github.io](https://hirakcoder.github.io)
