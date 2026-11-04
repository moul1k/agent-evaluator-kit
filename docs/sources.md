# Source lineage and reuse boundary

Inspected 2026-11-04:

| Source | Pinned commit | Reused contribution |
|---|---|---|
| [Moulik: transcription_agent_eval](https://github.com/moul1k/transciption_agent_eval) | `61f2714` | Extracted/adapted meta-evaluation, offline review, reporting, repeat analysis, cluster bootstrap and provenance |
| [Aayush: benchmarking-evaluation-layer](https://github.com/Aayushx9/benchmarking-evaluation-layer) | `1aa83e6eedab4c7438f7c4184bf482096f99d8dc` | Inspected evaluator/checks.py, evaluator.py, llm_judge.py and benchmark/cases.json; implemented trace-format adapter, explicit deterministic/model plugin separation, original structured numerical check and negative-control contract auditing |
| [Srihari: scheduler-eval](https://github.com/Srihari4589/scheduler-eval) | `cb1084253388eb5d452618c36cf1dadaf0359ed4` | Inspected schemas.py, runner.py, stats.py, judge.py, judge_eval.py; implemented run-format adapter, original strict-gate/correction-exercise helpers; retained group-aware uncertainty and human consensus from Moulik's core |

No LICENSE/COPYING files were present in either collaborator repository at these inspected commits. Public visibility does not itself grant redistribution permission. Consequently **no collaborator source, prompts, datasets, reports or fixtures are copied into this repository**. The integration consists of original implementations of general evaluation patterns and compatibility mappings for their documented formats. Obtain explicit permission before vendoring their domain-specific engines. This is not a legal determination.

The extracted code from Moulik's project is used at its owner's request. No blanket third-party license is asserted for the combined project. Public publication is authorized by the owner; collaborator implementations remain in their own repositories and are not redistributed here. The optional native bridges execute separately installed checkouts at explicit pinned revisions. Obtain contributor agreement before vendoring code or choosing a license intended to cover it.

See [three-project integration](three-project-integration.md) for the direct-extraction versus native-execution capability matrix and source-engine regression checks.

## Deliberate changes

- No automatic model fallback: judge failures are errors, not silently substituted deterministic scores.
- No averaging of unrelated dimensions to hide a critical failure.
- No grader labels or structured private correction targets in judge requests.
- A proposed scheduler output is not represented as a verified calendar state.
- Missing evidence is an explicit abstention, not an automatic pass.
- Synthetic labels and human consensus are separate reference types.

## Method references

- [Hamel: scoped evaluations](https://hamel.dev/blog/posts/evals/) — development workflow inspiration, not a claim of comprehensive compliance.
- [OpenAI: evaluation best practices](https://developers.openai.com/api/docs/guides/evaluation-best-practices) — scoped criteria and human calibration.
- [Langfuse SDK](https://langfuse.com/docs/observability/sdk/overview) — observation-based tracing. This implementation intentionally targets the installed v4 interface; current v5 migration is not claimed tested.
