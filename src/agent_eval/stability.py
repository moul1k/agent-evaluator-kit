"""Repeated-judgment consistency, distinct from agreement with human references."""

from itertools import combinations

from .meta import Submission, validate_submission


def analyze_repeats(bundle: dict, submissions: list[Submission], split: str) -> dict:
    if len(submissions) < 2:
        raise ValueError("at least two repeated judge submissions required")
    if len({s.evaluator_id for s in submissions}) != len(submissions):
        raise ValueError("repeat run IDs must be unique")
    for submission in submissions:
        validate_submission(submission, bundle)
        if submission.kind != "judge":
            raise ValueError("only judge submissions can be repeated")
    configurations = {s.metadata.get("configuration_hash") for s in submissions}
    if len(configurations) != 1 or None in configurations:
        raise ValueError("repeats require one shared configuration_hash")
    matrices = [{(j.case_id, j.criterion_id): j.verdict for j in s.judgments} for s in submissions]
    rows = []
    for case in bundle["cases"]:
        if case["split"] != split:
            continue
        for criterion in bundle["rubric"]["criteria"]:
            key = (case["id"], criterion["id"])
            votes = [matrix.get(key) for matrix in matrices]
            binary = [v for v in votes if v in ("pass", "fail")]
            pairs = list(combinations(binary, 2))
            rows.append(
                {
                    "case_id": key[0],
                    "criterion_id": key[1],
                    "verdicts": votes,
                    "binary_count": len(binary),
                    "pair_count": len(pairs),
                    "agreement_count": sum(a == b for a, b in pairs),
                    "complete_binary": len(binary) == len(votes),
                    "stable": len(binary) == len(votes) and len(set(binary)) == 1,
                }
            )
    if not rows:
        raise ValueError("no cases in selected split")
    total_pairs = sum(r["pair_count"] for r in rows)
    potential = len(rows) * len(submissions) * (len(submissions) - 1) // 2
    return {
        "schema_version": "1",
        "dataset_hash": bundle["dataset_hash"],
        "rubric_hash": bundle["rubric_hash"],
        "configuration_hash": configurations.pop(),
        "split": split,
        "runs": [s.evaluator_id for s in submissions],
        "limitation": "Consistency is not correctness; stable wrong judges can score perfectly.",
        "binary_pair_coverage": total_pairs / potential,
        "binary_pair_agreement": sum(r["agreement_count"] for r in rows) / total_pairs
        if total_pairs
        else None,
        "complete_cell_rate": sum(r["complete_binary"] for r in rows) / len(rows),
        "stable_cell_rate": sum(r["stable"] for r in rows) / len(rows),
        "cells": rows,
    }
