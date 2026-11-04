"""One shared runner for deterministic, subprocess, and model plugins."""

import time
from datetime import UTC, datetime

from .meta import Criterion, Judgment, Submission, digest
from .provenance import capture
from .schemas import EvalCase
from .tracing import safe_observation


def run(
    bundle,
    evaluator,
    evaluator_id,
    split="test",
    tracer=None,
    configuration=None,
    max_calls=100,
    verify_traces=False,
):
    cases = [EvalCase.model_validate(c) for c in bundle["cases"] if c["split"] == split]
    if not cases:
        raise ValueError("no cases in selected split")
    planned = len(cases) * len(bundle["rubric"]["criteria"])
    if max_calls <= 0 or planned > max_calls:
        raise ValueError("planned evaluations exceed positive max_calls; no calls made")
    judgments, errors, timings, traces, tracing_errors = [], [], [], [], []
    usage_rows, skipped, halted = [], [], False
    config_hash = digest(
        configuration
        or getattr(evaluator, "configuration", None)
        or {"plugin": type(evaluator).__name__}
    )
    verification = {"status": "not_requested"}
    try:
        for case in cases:
            for raw in bundle["rubric"]["criteria"]:
                criterion = Criterion.model_validate(raw)
                if halted:
                    skipped.append({"case_id": case.id, "criterion_id": criterion.id})
                    continue
                started = time.perf_counter()
                metadata = {
                    "case_id": case.id,
                    "group_id": case.group_id,
                    "criterion_id": criterion.id,
                    "configuration_hash": config_hash,
                    "dataset_hash": bundle["dataset_hash"],
                    "rubric_hash": bundle["rubric_hash"],
                }
                with safe_observation(
                    tracer,
                    metadata,
                    {
                        "case": case.model_dump(mode="json"),
                        "criterion": raw,
                    },
                    tracing_errors,
                ) as span:
                    # Catch inside span: third-party exceptions may embed private data.
                    try:
                        judgment = Judgment.model_validate(evaluator.evaluate(case, criterion))
                        if judgment.case_id != case.id or judgment.criterion_id != criterion.id:
                            raise ValueError("wrong case/criterion identity")
                        judgments.append(judgment)
                    except Exception as exc:
                        errors.append({**metadata, "error_type": type(exc).__name__})
                        status_code = getattr(exc, "status_code", None)
                        if status_code in (401, 403, 429):
                            halted = True
                            errors[-1]["http_status"] = status_code
                        if span:
                            try:
                                span.update(level="ERROR", status_message=type(exc).__name__)
                            except Exception as trace_exc:
                                tracing_errors.append({"error_type": type(trace_exc).__name__})
                    else:
                        if span:
                            try:
                                tracer.record(
                                    span, judgment, usage=getattr(evaluator, "last_usage", {})
                                )
                                traces.append({**metadata, "trace_id": span.trace_id})
                            except Exception as exc:
                                tracing_errors.append({"error_type": type(exc).__name__})
                    usage = getattr(evaluator, "last_usage", {})
                    if usage:
                        usage_rows.append({**metadata, **usage})
                timings.append(
                    {**metadata, "latency_ms": round((time.perf_counter() - started) * 1000, 2)}
                )
    finally:
        if tracer:
            try:
                tracer.flush()
                if verify_traces and traces:
                    verification = tracer.verify_trace(traces[0]["trace_id"])
            except Exception as exc:
                tracing_errors.append({"error_type": type(exc).__name__})
    return Submission(
        dataset_hash=bundle["dataset_hash"],
        rubric_hash=bundle["rubric_hash"],
        rubric_id=bundle["rubric"]["id"],
        rubric_version=bundle["rubric"]["version"],
        evaluator_id=evaluator_id,
        kind="judge",
        created_at=datetime.now(UTC),
        judgments=judgments,
        metadata={
            "errors": errors,
            "timings": timings,
            "traces": traces,
            "tracing_errors": tracing_errors,
            "trace_verification": verification,
            "provider_usage": usage_rows,
            "skipped": skipped,
            "planned_evaluations": planned,
            "split": split,
            "configuration_hash": config_hash,
            "provenance": capture(),
        },
    )
