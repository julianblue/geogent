# geogent agent evals

Golden-trajectory evals for the LangGraph agent. `cases/core.yaml` is the
single source of truth for cases; everything else consumes it.

## Layout

| module                 | role |
| ---------------------- | ---- |
| `cases/core.yaml`      | golden cases (inputs + expectations), reviewed in PRs |
| `dataset.py`           | typed loader (`EvalCase` / `Expectation`), fails loudly on bad YAML |
| `runner.py`            | drives a live `langgraph dev` server, auto-resumes UI interrupts |
| `scorers.py`           | four deterministic scorers (tools, args, length, final keywords) |
| `agentevals_bridge.py` | state-dict → agentevals shapes; trajectory superset match; strict graph-steps match; openevals LLM judge |
| `report.py`            | `score_case` (all scorers, one gating rule), table rendering |
| `langsmith_dataset.py` | syncs the YAML into a LangSmith hosted dataset (diff by stable uuid5 ids) |
| `experiment.py`        | `aevaluate` experimentation CLI (concurrency, repetitions, model A/B) |
| `recordings/`          | committed `threads.get_state` snapshots from live runs |

## Entry points

**1. CI gate (pytest, live):** `uv run pytest -m eval -s` — runs every case
once, serially, and gates pass/fail (xfail-aware). Skips without
`OPENROUTER_API_KEY`. With `LANGSMITH_API_KEY` set, the per-case tests also
log a LangSmith *test-suite experiment* via `@pytest.mark.langsmith`; without
it, tracking degrades to a no-op.

**2. Experimentation (aevaluate, live):** `make eval-experiment` or
`uv run python -m tests.evals.experiment --model ... --repetitions 5 --concurrency 4`.
Needs `LANGSMITH_API_KEY` + `OPENROUTER_API_KEY`. Syncs the dataset first
(`--skip-sync` to skip; `make eval-sync` to sync alone), then runs cases
concurrently with repetitions and logs a hosted *dataset experiment* —
use this for model comparisons and flake rates, not CI. The judge model is
pinned independently of `--model` (`--judge-model` / `GEOGENT_EVAL_JUDGE_MODEL`)
so comparisons aren't skewed.

**3. Offline replay (pytest, no key):** part of the normal `make test` run.
`test_replay.py` re-scores the committed recordings with the deterministic
scorers, so scorer/expectation changes are regression-tested offline. Refresh
recordings with `GEOGENT_EVAL_RECORD=1 uv run pytest -m eval`.

Note the three LangSmith write paths are distinct artifacts: pytest-plugin
test-suite rows (1), `maybe_push_to_langsmith` run+feedback rows (1), and
hosted dataset experiments (2). They coexist; compare like with like.

## Scorers per case

`tool_selection`, `args`, `length`, `final` (deterministic), plus
`trajectory_match` (agentevals superset over required tool calls). Two opt-in:

- `final_judge` — LLM-as-judge for final-answer quality; applies only to cases
  *without* `final_contains_any` (free-form numeric output) and only when a
  judge is configured (live suite / experiments).
- `graph_steps` — agentevals strict per-turn node-step match; applies only to
  cases that pin `expect.graph_steps`. Adoption path: record several runs
  (`GEOGENT_EVAL_RECORD=1`), confirm the steps in the recordings agree, then
  pin them in YAML. Don't pin a case whose step sequence varies run to run.

## Adding a case

Add it to `core.yaml` (the loader rejects malformed cases and duplicate ids),
run the live suite, and if it's a known weakness of the default model, mark it
`xfail: "<reason>"` instead of letting it gate CI red. Re-record and commit
recordings when convenient, then `make eval-sync` to refresh the hosted
dataset (YAML edits never need to touch LangSmith directly).
