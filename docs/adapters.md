# Adapters and migration

The new package does not import or install any of the three agents. This keeps dependencies, agent execution and evaluator execution separate.

| Format | Input mapping | Output/evidence mapping | Intentionally excluded |
|---|---|---|---|
| Moulik transcription ReviewCase/ArtifactCase | input preserved; meeting_id -> group_id | output, tool_trace, final_state preserved | expected labels; old artifact_type marker |
| Aayush trace JSON | question + dataset_schema (inspection fallback) | final_answer/answer, numerical_evidence/evidence; plan/code/errors in trace; execution_result/result in final_state | benchmark labels and existing evaluator scores |
| Srihari individual CaseResult + ScenarioCase | scenario.input + correction.text | last raw_schedule as output, all raw schedules as turns | report/grade, structured correction targets; final_state remains null |

CLI converts one source object to one JSONL row, creating a new output file:

```bash
agent-eval convert trace.json analysis.jsonl --format analysis --case-id a1 --group-id dataset-question-1
agent-eval convert case-result.json schedule.jsonl --format scheduler --scenario scenario.json
agent-eval convert review-case.json meeting.jsonl --format transcription
```

For a scheduler run report, select each item from `cases` and join its `case_id` to a scenario ID first. For JSONL transcription inputs, parse individual lines. Python functions in `agent_eval.adapters` support batch use. Callers must assign distinct candidate IDs for repeated schedules and keep their group IDs fixed.

Dataset identity matters: include dataset revision/schema identifiers in analysis inputs when different datasets have the same question. Groups represent independent source scenarios, not individual mutations or repeated calls. The framework cannot automatically infer semantic dataset leakage.

Existing annotation submissions need deliberate migration: changing case fields changes the dataset hash. Never overwrite an old hash to make labels pass validation. Rebuild the review bundle and record an audited mapping/review decision.

## What is not extracted

The upstream implementations remain upstream; no collaborator code is vendored. Optional [native bridges](three-project-integration.md) now execute the original full five-dimension analysis engine and scheduler final/correction/regression engine from pinned local checkouts. The lighter original schedule plugin remains available without those checkouts and abstains on unresolved text corrections. Gemini clients, upstream agent planners and qualitative LLM prompts are not bundled or automatically invoked. Connect qualitative judges through the common callable/subprocess interface or a versioned model rubric.
