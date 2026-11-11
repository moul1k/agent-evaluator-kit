# Agent Evaluator Kit

A standalone, agent-neutral toolkit for **evaluating agents and auditing the judges that evaluate them**. Research prototype, not a validated production benchmark.

Extracted from the transcription evaluation project; integrates format adapters and design patterns identified in Aayush's data-analysis evaluator and Srihari's scheduler evaluation work. See [source attribution](docs/sources.md) for exact commits and reuse boundaries.

## Quick start (no API key or model spend)

```bash
python -m venv .venv
# Activate: Windows .venv\Scripts\activate; Unix source .venv/bin/activate
pip install -e ".[dev]"
pytest
agent-eval demo artifacts/demo
```

The demo creates six original synthetic cases across three domain tags, an offline human-review page, typed judge submissions, and an authored-contract audit. It intentionally uses a **narrow numerical-evidence check**, not a full scheduler or transcript evaluator.

Expected smoke results: numerical checker 6/6 matches, always-pass negative control 3/6 matches and three false acceptances. These are engineering sanity checks, **not human-validated accuracy**.

## Plug in an agent

Export one JSON object per line:

```json
{"id":"run-1","group_id":"scenario-1","split":"test","input":{"request":"Count completed jobs"},"output":{"numerical_evidence":3},"tool_trace":[],"final_state":{"execution_result":3}}
```

`input` is an arbitrary JSON object; `output` is any JSON value. `final_state: null` means unavailable. It must be independently captured evidence, not a copy of the assistant's success claim. Keep related variants in one group and split. The loader rejects group/split and identical-input leakage.

Create a rubric with `id`, `version`, and criteria containing `id`, `question`, `pass_condition`, `fail_condition`. All plugins return `case_id`, `criterion_id`, `verdict`, `rationale`, `evidence`. Verdicts: pass/fail/insufficient_context/not_applicable.

```bash
agent-eval prepare cases.jsonl rubric.json artifacts/review
agent-eval run cases.jsonl rubric.json numeric.json numeric-v1 --plugin numeric
agent-eval validate cases.jsonl rubric.json numeric.json
```

### Any language/model via subprocess

```bash
agent-eval run cases.jsonl rubric.json judge.json external-v1 --plugin subprocess --command-json '["python","my_judge.py"]'
```

The subprocess receives one JSON request on stdin and returns a judgment JSON on stdout. No shell interpretation; 60-second timeout. Reference labels are never part of the request. Only run trusted executable adapters: this is not a sandbox.

### OpenAI model judge (paid, explicit)

```bash
pip install -e ".[openai,langfuse]"
# Set OPENAI_API_KEY and the three LANGFUSE_* variables in your shell.
agent-eval run cases.jsonl rubric.json judge.json luna-v1 --plugin openai --model gpt-6-luna --langfuse
```

One request per selected case × criterion; no retries, 1,000 output-token cap per request. This is **not a dollar budget cap**. Inspect dataset size before paid runs. No agent is executed by the evaluator; bring its captured artifacts.

### Embedded Python

```python
from agent_eval import load_bundle
from agent_eval.runner import run
from agent_eval.evaluators import NumericResultEvaluator

bundle = load_bundle(cases_path, rubric_path)  # pathlib.Path values
submission = run(
    bundle,
    NumericResultEvaluator(),
    "numeric-v1",
    configuration={"plugin": "numeric", "version": "1"},
)
```

Implement `evaluate(case, criterion) -> Judgment` to add a Python plugin. Supply a complete, nonsecret configuration fingerprint when comparing repeat runs.

## Human review and judge auditing

Open `review.html` locally. Two reviewers independently export annotations; they do not see model verdicts or reference labels. Preserve critiques about missing or misleading rubric questions. There is no server, login, automatic saving, or identity verification; the study organizer enforces reviewer independence.

Put only compatible submissions in a directory:

```bash
agent-eval compare cases.jsonl rubric.json submissions artifacts/comparison
agent-eval repeats cases.jsonl rubric.json repeated-submissions stability.json
agent-eval audit cases.jsonl rubric.json judge.json contracts.json audit.json
```

Comparison requires two unanimous binary human votes or an explicit adjudication. Disagreement stays unresolved. It reports failure precision/detection, false acceptance/rejection, missingness, abstention, coverage, pair agreement, group-cluster bootstrap intervals, and an evidence-bearing review queue. Repeat consistency is separate: a judge can be stably wrong. A contract audit uses **authored specifications**, never manufactures human consensus.

`strict_gate` requires every named dimension to pass; missing or abstaining dimensions fail. `correction_effect` distinguishes actually exercised corrections from no-op successes.

The original `schedule` plugin checks required/unknown/duplicate assignments, work hours, shared-attendee overlaps, blocked intervals, fixed days, earliest starts, and deadline days. Use criterion ID `schedule_hard_constraints` and scheduler-adapter input shape. It abstains when a natural-language correction has not been resolved into explicit constraints. It does not judge soft quality or verify calendar writes.

## Langfuse

For `run`, cloud tracing automatically enables when both Langfuse keys are configured; `--no-langfuse` forces local-only. Without credentials it stays local. The runner creates evaluator observations, categorical criterion scores, and trace IDs, includes dataset/rubric/configuration hashes, and flushes at completion. With default privacy settings, artifacts and rationales are not uploaded; IDs, hashes, verdicts and provider token counts are. Add `--trace-content` only after reviewing data-sharing permissions. Do not put secrets or personal data in case/group IDs.

The optional integration pins Python SDK `>=4.17,<5`, matching the tested SDK interface. New SDK majors require compatibility testing. A successful SDK flush is not proof of backend ingestion; verify trace IDs in Langfuse. Check `metadata.errors` and `metadata.tracing_errors`; CLI runs exit nonzero for recorded errors. Missing predictions remain visible.

## Mentor materials

- [Architecture, evidence, demo narrative, next milestones](docs/mentor-brief.md)
- [Source mapping and licensing](docs/sources.md)
- [Source format adapters and migration](docs/adapters.md)
- [Study protocol](docs/study-protocol.md)
- [Verification record](docs/verification.md)
- [Plug-and-play recipes and runtime credentials](docs/plug-and-play.md)
- [Verified live GPT-6 Luna + Langfuse smoke test](docs/live-smoke-2026-11-04.md)
- [All three projects: capability matrix and native engine bridges](docs/three-project-integration.md)
- [Study runner: frozen batches, human collection and evaluator reports](docs/study-runner.md)
- [Provisional AI annotations and traced pilot results](docs/ai-annotation-pilot-2026-11-11.md)

No private transcripts, API keys, original project artifacts, or upstream source files are bundled. CI uses no credentials or paid calls.
