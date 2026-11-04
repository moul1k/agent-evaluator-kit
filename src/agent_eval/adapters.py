"""Explicit mappings for the three inspected source formats; no source imports."""

from .schemas import EvalCase


def transcription(raw: dict) -> EvalCase:
    return EvalCase(
        id=raw["id"],
        group_id=raw["meeting_id"],
        split=raw["split"],
        input=raw["input"],
        output=raw["output"],
        tool_trace=raw.get("tool_trace", []),
        final_state=raw.get("final_state"),
    )


def data_analysis(raw: dict, case_id: str, group_id: str, split: str = "test") -> EvalCase:
    def pick(new, old, default=None):
        return raw[new] if new in raw else raw.get(old, default)

    return EvalCase(
        id=case_id,
        group_id=group_id,
        split=split,
        input={
            "question": raw["question"],
            "dataset_schema": pick("dataset_schema", "inspection", {}),
        },
        output={
            "answer": pick("final_answer", "answer", ""),
            "numerical_evidence": pick("numerical_evidence", "evidence"),
        },
        tool_trace=[
            {
                "plan": pick("analysis_plan", "plan", {}),
                "code": pick("generated_code", "code_used", ""),
                "errors": pick("errors", "error"),
            }
        ],
        final_state={"execution_result": pick("execution_result", "result")},
    )


def scheduler(scenario: dict, result: dict, split: str = "test") -> EvalCase:
    if scenario["id"] != result["case_id"]:
        raise ValueError("scenario/result IDs differ")
    if result.get("error") or not result.get("raw_schedules"):
        raise ValueError("cannot convert failed or empty scheduler run")
    correction = scenario.get("correction")
    # Structured correction fields contain grader-only truth in the upstream format.
    return EvalCase(
        id=result["case_id"],
        group_id=scenario["id"],
        split=split,
        input={
            "scenario": scenario["input"],
            "correction_text": correction.get("text") if correction else None,
        },
        output=result["raw_schedules"][-1],
        tool_trace=[{"turn": i + 1, "schedule": s} for i, s in enumerate(result["raw_schedules"])],
        # A proposed schedule is NOT evidence of a calendar write.
        final_state=None,
    )
