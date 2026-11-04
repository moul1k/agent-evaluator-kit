"""Trusted local plugin process. No model calls and no upstream code redistribution."""

import json
import os
import sys
from pathlib import Path


def analysis(case):
    from src.evaluator import evaluate_trace

    evidence = case["tool_trace"][0]
    trace = {
        "question": case["input"]["question"],
        "dataset_schema": case["input"]["dataset_schema"],
        "analysis_plan": evidence["plan"],
        "generated_code": evidence["code"],
        "execution_result": (case["final_state"] or {}).get("execution_result"),
        "final_answer": case["output"]["answer"],
        "numerical_evidence": case["output"]["numerical_evidence"],
        "errors": evidence["errors"],
    }
    report = evaluate_trace(trace, trace_id=case["id"])
    return {
        "scores": report["scores"],
        "explanations": report["explanations"],
        "evidence": [issue["message"] for issue in report["issues"]],
    }


def scheduler(case, context):
    from scheduler_eval.grader import correction_compliance, grade_final
    from scheduler_eval.runner import _apply_correction_to_scenario
    from scheduler_eval.schemas import ScenarioCase, ScenarioInput, ScheduleOutput

    raw = context or {
        "id": case["group_id"],
        "description": "Adapter case",
        "input": case["input"]["scenario"],
        "correction": None,
    }
    scenario = ScenarioCase.model_validate(raw)
    adapted_input = ScenarioInput.model_validate(case["input"]["scenario"])
    if scenario.id != case["group_id"] or scenario.input != adapted_input:
        raise ValueError("native scenario context does not match adapted case")
    text = scenario.correction.text if scenario.correction else None
    if text != case["input"].get("correction_text"):
        raise ValueError("matching private correction specification is required")
    final_input, originals = _apply_correction_to_scenario(scenario.input, scenario)
    final = ScheduleOutput.model_validate(case["output"])
    report = grade_final(
        final,
        final_input,
        original_meetings=originals if scenario.correction else None,
        correction=scenario.correction,
    )
    if scenario.correction:
        first = ScheduleOutput.model_validate(case["tool_trace"][0]["schedule"])
        before = correction_compliance(first, scenario.correction, final_input.meetings)
        report["correction_exercised"] = float(any(v == 0 for v in before.values()))
    scores = {k: v for k, v in report.items() if isinstance(v, (int, float))}
    evidence = report["hard_violations"] + report.get("regression_violations", [])
    return {"scores": scores, "evidence": evidence}


def main():
    project, repository = sys.argv[1:]
    # Native bridges are deterministic-only even when the parent has model credentials.
    for key in ("OPENAI_API_KEY", "GEMINI_API_KEY", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
        os.environ.pop(key, None)
    request = json.load(sys.stdin)
    root = Path(repository).resolve(strict=True)
    sys.path.insert(0, str(root if project == "analysis" else root / "src"))
    report = (
        analysis(request["case"])
        if project == "analysis"
        else scheduler(request["case"], request.get("context"))
    )
    print(json.dumps(report))


if __name__ == "__main__":
    main()
