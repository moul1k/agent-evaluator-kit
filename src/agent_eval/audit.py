"""Authored contract audits are distinct from human-consensus comparisons."""

from .meta import validate_submission
from .schemas import StrictModel


class Contract(StrictModel):
    case_id: str
    criterion_id: str
    expected: str
    defect: str


def audit(bundle, submission, contracts):
    validate_submission(submission, bundle)
    allowed = {(c["id"], r["id"]) for c in bundle["cases"] for r in bundle["rubric"]["criteria"]}
    keys = [(c.case_id, c.criterion_id) for c in contracts]
    if not keys or len(keys) != len(set(keys)) or not set(keys) <= allowed:
        raise ValueError("empty, duplicate, or unknown contract cells")
    if any(
        c.expected not in ("pass", "fail", "insufficient_context", "not_applicable")
        for c in contracts
    ):
        raise ValueError("invalid expected verdict")
    predictions = {(j.case_id, j.criterion_id): j.verdict for j in submission.judgments}
    rows = [
        {**c.model_dump(), "predicted": predictions.get((c.case_id, c.criterion_id))}
        for c in contracts
    ]
    n = len(rows)
    return {
        "reference_type": "authored_synthetic_contracts",
        "cells": n,
        "match_rate": sum(r["expected"] == r["predicted"] for r in rows) / n,
        "missing": sum(r["predicted"] is None for r in rows),
        "false_acceptances": sum(
            r["expected"] == "fail" and r["predicted"] == "pass" for r in rows
        ),
        "false_rejections": sum(r["expected"] == "pass" and r["predicted"] == "fail" for r in rows),
        "rows": rows,
        "limitation": "Authored synthetic expectations are not independent human labels.",
    }
