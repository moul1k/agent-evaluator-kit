# Three projects, one evaluation contract

## Included capabilities and exact boundaries

| Source | Included directly | Complete original engine available through bridge | Shared downstream layer |
|---|---|---|---|
| Moulik's transcription evaluator | Adapted human review, meta-evaluation, adjudication, hashed datasets/rubrics, repeat consistency, group bootstrap, reporting and provenance | Existing custom judges via callable/subprocess; no dependency on the transcript agent | Same typed judgments, human submissions, review queue and optional Langfuse instrumentation |
| Aayush's data-analysis evaluator | New/legacy trace-key adapter, numerical-evidence checker, authored-contract auditing and negative control | `NativeEvaluator("analysis", ...)` invokes original five-dimension evaluate_trace: numerical correctness, grounding, method, completeness and hallucination checks | Same typed judgments, thresholds, audit/compare pipeline and tracing |
| Srihari's scheduler evaluator | Scenario/result adapter, original hard-constraint checker, strict gates and correction-exercise helper | `NativeEvaluator("scheduler", ...)` invokes original grade_final plus correction resolution: hard rules, preferences, regression and correction-specific compliance | Same typed judgments, thresholds, audit/compare pipeline and tracing |

The optional native bridges **execute separately installed, trusted source checkouts**. The repository does not vendor collaborator source, fixtures or prompts. Their qualitative model judges can be connected through the common callable/subprocess interfaces, or replaced by a common versioned rubric and model judge. Those optional upstream LLM/Gemini paths are not automatically invoked or claimed behavior-equivalent.

## One consistent interpretation

1. Source adapters produce EvalCase; domain labels/oracle targets are not ordinary model-judge inputs.
2. Deterministic checks and model judges retain distinct identities. We do not average them to conceal failure or silently fall back from one to the other.
3. Native continuous scores are converted only through **explicit per-criterion thresholds** recorded in the configuration hash. Missing/not-applicable dimensions return not_applicable, never pass. Invalid scores fail the invocation.
4. Native scheduler correction specifications live in a separate context mapping used only by the trusted deterministic bridge. The worker checks that source scenario and correction text match the adapted case. The grading context is never added to the case or human/model review bundle.
5. All routes use the same runner, structured judgments, human comparison, authored audits, missingness handling and optional Langfuse tracer.
6. Each domain needs its own appropriate rubric or a carefully specified shared one. Do not grade every scheduler against data-analysis criteria. DomainRouter selects by caller-supplied classification; RoutedEvaluator can then select by criterion.

## Install native engines without copying them

Clone the sources separately and check out the commits in docs/sources.md. Review them as executable code; this is **not a sandbox**. Install their dependencies in the same environment as this package (or pass a Python executable where this package and their dependencies are installed). Native bridges remove provider keys from their child process and do not call model judges.

```python
from pathlib import Path
from agent_eval import NativeEvaluator

analysis = NativeEvaluator(
    "analysis",
    Path("../benchmarking-evaluation-layer"),
    {
        "numerical_correctness": 0.9,
        "data_grounding": 0.9,
        "method_correctness": 0.9,
        "completeness": 0.9,
        "hallucination_free": 0.9,
    },
    expected_commit="1aa83e6eedab4c7438f7c4184bf482096f99d8dc",
)

scheduler = NativeEvaluator(
    "scheduler",
    Path("../scheduler-eval"),
    {"hard_pass": 1.0, "regression_score": 1.0, "removed_meeting_absent": 1.0},
    expected_commit="cb1084253388eb5d452618c36cf1dadaf0359ed4",
    contexts={"candidate-id": original_scenario_case},
)
```

Thresholds above are examples, not a validated cross-domain policy. Native bridge commit checks reject unexpected revisions. Context mappings and thresholds are fingerprinted. Native execution is deterministic-only; soft LLM judgments should use a separately versioned model route. Upstream bug fixes or changed semantics require a new pin and regression tests.

CLI equivalent:

```bash
agent-eval run cases.jsonl rubric.json native.json native-v1 --plugin native-analysis --native-repository ../benchmarking-evaluation-layer --native-commit 1aa83e6eedab4c7438f7c4184bf482096f99d8dc --native-thresholds-json '{"numerical_correctness":0.9}'
```

For scheduler use `--plugin native-scheduler` and `--native-contexts contexts.json` containing `{case_id: original_scenario_case}`. Do not commit private contexts. Native sources and runtime dependency installation remain the deployer's responsibility.

## Verification

Local integration tests execute both pinned original engines with original synthetic fixtures. They verify all five analysis dimensions, detection of wrong numerical evidence, scheduler cancellation compliance, regression preservation, exercised correction and rejection of an ignored cancellation. Ordinary unit tests skip these two source-dependent checks unless AAYUSH_REPO and SRIHARI_REPO are set. A separate CI job checks out the two pinned public sources and runs the bridge tests; it makes no model calls and does not publish upstream source artifacts.

```powershell
$env:AAYUSH_REPO = "C:/path/benchmarking-evaluation-layer"
$env:SRIHARI_REPO = "C:/path/scheduler-eval"
pytest tests/test_native.py
```

This establishes interoperability and a few regression properties, **not universal agreement between domain graders or independent human accuracy**.
