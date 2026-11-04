"""One shared runner for deterministic, subprocess, and model plugins."""

import time
from contextlib import nullcontext
from datetime import UTC, datetime

from .meta import Criterion, Submission, digest
from .provenance import capture
from .schemas import EvalCase


def run(bundle, evaluator, evaluator_id, split="test", tracer=None, configuration=None):
    cases = [EvalCase.model_validate(c) for c in bundle["cases"] if c["split"] == split]
    if not cases:
        raise ValueError("no cases in selected split")
    judgments, errors, timings, traces, tracing_errors = [], [], [], [], []
    config_hash = digest(configuration or {"plugin": type(evaluator).__name__})
    try:
        for case in cases:
            for raw in bundle["rubric"]["criteria"]:
                criterion = Criterion.model_validate(raw)
                started = time.perf_counter()
                metadata = {
                    "case_id": case.id,
                    "group_id": case.group_id,
                    "criterion_id": criterion.id,
                    "configuration_hash": config_hash,
                    "dataset_hash": bundle["dataset_hash"],
                    "rubric_hash": bundle["rubric_hash"],
                }
                context = (
                    tracer.observation(
                        metadata,
                        {
                            "case": case.model_dump(mode="json"),
                            "criterion": raw,
                        },
                    )
                    if tracer
                    else nullcontext(None)
                )
                with context as span:
                    # Catch inside span: third-party exceptions may embed private data.
                    try:
                        judgment = evaluator.evaluate(case, criterion)
                        if judgment.case_id != case.id or judgment.criterion_id != criterion.id:
                            raise ValueError("wrong case/criterion identity")
                        judgments.append(judgment)
                    except Exception as exc:
                        errors.append({**metadata, "error_type": type(exc).__name__})
                        if span:
                            span.update(level="ERROR", status_message=type(exc).__name__)
                    else:
                        if span:
                            try:
                                tracer.record(span, judgment)
                                traces.append({**metadata, "trace_id": span.trace_id})
                            except Exception as exc:
                                tracing_errors.append({"error_type": type(exc).__name__})
                timings.append(
                    {**metadata, "latency_ms": round((time.perf_counter() - started) * 1000, 2)}
                )
    finally:
        if tracer:
            try:
                tracer.flush()
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
            "split": split,
            "configuration_hash": config_hash,
            "provenance": capture(),
        },
    )
