"""Portable, strictly validated evaluator and human annotation contracts."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from .schemas import EvalCase, StrictModel
from .uncertainty import bootstrap_detection

Verdict = Literal["pass", "fail", "insufficient_context", "not_applicable"]


class Criterion(StrictModel):
    id: str
    question: str
    pass_condition: str
    fail_condition: str


class Rubric(StrictModel):
    id: str
    version: str
    criteria: list[Criterion] = Field(min_length=1)

    @model_validator(mode="after")
    def unique(self):
        if any(c.id == "all" for c in self.criteria):
            raise ValueError("criterion ID all is reserved for aggregate metrics")
        if len({c.id for c in self.criteria}) != len(self.criteria):
            raise ValueError("duplicate criterion IDs")
        return self


class Judgment(StrictModel):
    case_id: str
    criterion_id: str
    verdict: Verdict
    rationale: str = Field(min_length=1)
    evidence: list[str] = Field(default_factory=list)


class Submission(StrictModel):
    schema_version: Literal["1"] = "1"
    dataset_hash: str
    rubric_hash: str
    rubric_id: str
    rubric_version: str
    evaluator_id: str = Field(min_length=1)
    kind: Literal["human", "judge", "adjudication"]
    created_at: datetime
    judgments: list[Judgment]
    metadata: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def unique(self):
        keys = [(j.case_id, j.criterion_id) for j in self.judgments]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate case/criterion judgment")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must include a timezone")
        return self


def digest(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def load_bundle(cases_path: Path, rubric_path: Path) -> dict:
    cases = []
    for number, line in enumerate(cases_path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            try:
                raw = json.loads(line)
                cases.append(EvalCase.model_validate(raw))
            except ValueError as exc:
                raise ValueError(f"{cases_path}:{number}: {exc}") from exc
    rubric = Rubric.model_validate_json(rubric_path.read_text(encoding="utf-8"))
    return bundle_from_cases(cases, rubric)


def bundle_from_cases(cases, rubric: Rubric) -> dict:
    cases = [c if isinstance(c, EvalCase) else EvalCase.model_validate(c) for c in cases]
    rubric = Rubric.model_validate(rubric)
    if not cases or len({c.id for c in cases}) != len(cases):
        raise ValueError("dataset must be nonempty with unique case IDs")
    meetings = {}
    input_splits = {}
    for case in cases:
        signature = (case.split, digest(case.input))
        if case.group_id in meetings and meetings[case.group_id] != signature:
            raise ValueError("group variants must share a split and input")
        meetings[case.group_id] = signature
        input_hash = digest(case.input)
        if input_hash in input_splits and input_splits[input_hash] != case.split:
            raise ValueError("identical input cannot cross splits under different IDs")
        input_splits[input_hash] = case.split
    case_data = [c.model_dump(mode="json") for c in cases]
    rubric_data = rubric.model_dump(mode="json")
    return {
        "cases": case_data,
        "rubric": rubric_data,
        "dataset_hash": digest(case_data),
        "rubric_hash": digest(rubric_data),
    }


def validate_submission(submission: Submission, bundle: dict) -> None:
    if (
        submission.dataset_hash != bundle["dataset_hash"]
        or submission.rubric_hash != bundle["rubric_hash"]
        or submission.rubric_id != bundle["rubric"]["id"]
        or submission.rubric_version != bundle["rubric"]["version"]
    ):
        raise ValueError("submission dataset/rubric provenance mismatch")
    allowed = {(c["id"], r["id"]) for c in bundle["cases"] for r in bundle["rubric"]["criteria"]}
    for judgment in submission.judgments:
        if (judgment.case_id, judgment.criterion_id) not in allowed:
            raise ValueError("unknown case or criterion")


def compare(bundle: dict, submissions: list[Submission], split: str = "test") -> dict:
    """Use independent human consensus; explicit adjudications resolve disagreements.

    Missing/abstaining predictions never disappear from coverage counts.
    """
    identities = [(s.kind, s.evaluator_id) for s in submissions]
    if len(identities) != len(set(identities)):
        raise ValueError("duplicate evaluator submission; merge intentionally before analysis")
    for submission in submissions:
        validate_submission(submission, bundle)
    keys = [
        (c["id"], r["id"])
        for c in bundle["cases"]
        if c["split"] == split
        for r in bundle["rubric"]["criteria"]
    ]
    if not keys:
        raise ValueError(f"no cases in split {split}")
    humans, adjudications, judges = defaultdict(list), defaultdict(list), {}
    for submission in submissions:
        values = {(j.case_id, j.criterion_id): j.verdict for j in submission.judgments}
        if submission.kind == "judge":
            judges[submission.evaluator_id] = values
        else:
            target = humans if submission.kind == "human" else adjudications
            for key, value in values.items():
                target[key].append(value)
    references, unresolved = {}, []
    for key in keys:
        votes = adjudications.get(key) or humans.get(key, [])
        minimum = 1 if adjudications.get(key) else 2
        if len(votes) >= minimum and len(set(votes)) == 1 and votes[0] in ("pass", "fail"):
            references[key] = votes[0]
        else:
            unresolved.append({"case_id": key[0], "criterion_id": key[1], "votes": votes})
    reports = {}
    for evaluator, predictions in judges.items():
        reports[evaluator] = {}
        for criterion in ["all"] + [r["id"] for r in bundle["rubric"]["criteria"]]:
            selected = {
                k: v for k, v in references.items() if criterion == "all" or k[1] == criterion
            }
            counts = {"tp": 0, "fp": 0, "tn": 0, "fn": 0, "missing": 0, "abstained": 0}
            for key, reference in selected.items():
                predicted = predictions.get(key)
                if predicted is None:
                    counts["missing"] += 1
                elif predicted not in ("pass", "fail"):
                    counts["abstained"] += 1
                else:
                    label = (
                        ("tp" if predicted == "fail" else "fn")
                        if reference == "fail"
                        else ("fp" if predicted == "fail" else "tn")
                    )
                    counts[label] += 1
            tp, fp, tn, fn = [counts[n] for n in ("tp", "fp", "tn", "fn")]

            def ratio(a, b):
                return a / b if b else None

            reports[evaluator][criterion] = dict(
                **counts,
                reference_count=len(selected),
                coverage=ratio(tp + fp + tn + fn, len(selected)),
                failure_precision=ratio(tp, tp + fp),
                failure_recall_answered=ratio(tp, tp + fn),
                failure_detection_rate=ratio(tp, sum(v == "fail" for v in selected.values())),
                failure_detection_ci95=bootstrap_detection(
                    selected, predictions, {c["id"]: c["group_id"] for c in bundle["cases"]}
                ),
                false_acceptance_rate_answered=ratio(fn, tp + fn),
                false_rejection_rate_answered=ratio(fp, tn + fp),
            )
    pair_agree = pair_total = 0
    for key in keys:
        votes = [v for v in humans[key] if v in ("pass", "fail")]
        for i, vote in enumerate(votes):
            for other in votes[i + 1 :]:
                pair_total += 1
                pair_agree += vote == other
    review_queue = []
    for key in keys:
        reasons = []
        reference = references.get(key)
        if reference is None:
            reasons.append("unresolved_reference")
        judge_rows = []
        for evaluator, predictions in judges.items():
            predicted = predictions.get(key)
            if predicted is None:
                reasons.append("missing_prediction")
            elif predicted not in ("pass", "fail"):
                reasons.append("judge_abstained")
            elif reference is not None and predicted != reference:
                reasons.append("false_acceptance" if reference == "fail" else "false_rejection")
            judge_rows.append({"evaluator_id": evaluator, "verdict": predicted})
        if reasons:
            annotations = []
            for submission in submissions:
                for judgment in submission.judgments:
                    if (judgment.case_id, judgment.criterion_id) == key:
                        annotations.append(
                            {
                                "evaluator_id": submission.evaluator_id,
                                "kind": submission.kind,
                                **judgment.model_dump(),
                            }
                        )
            review_queue.append(
                {
                    "case_id": key[0],
                    "criterion_id": key[1],
                    "reference": reference,
                    "reasons": sorted(set(reasons)),
                    "judges": judge_rows,
                    "annotations": annotations,
                }
            )
    from .provenance import capture

    critiques, human_completion = [], []
    selected_ids = {k[0] for k in keys}
    for submission in submissions:
        if submission.kind != "human":
            continue
        judgments = [j for j in submission.judgments if (j.case_id, j.criterion_id) in keys]
        human_completion.append(
            {
                "evaluator_id": submission.evaluator_id,
                "submitted_cells": len(judgments),
                "possible_cells": len(keys),
                "binary_cells": sum(j.verdict in ("pass", "fail") for j in judgments),
            }
        )
        notes = submission.metadata.get("freeform_critiques", {})
        if isinstance(notes, dict):
            for case_id, critique in notes.items():
                if case_id in selected_ids and isinstance(critique, str) and critique.strip():
                    critiques.append(
                        {
                            "case_id": case_id,
                            "reviewer": submission.evaluator_id,
                            "critique": critique,
                        }
                    )
    return {
        "schema_version": "1",
        "dataset_hash": bundle["dataset_hash"],
        "rubric_hash": bundle["rubric_hash"],
        "split": split,
        "reference_count": len(references),
        "unresolved": unresolved,
        "human_pair_comparisons": pair_total,
        "human_pair_agreement": pair_agree / pair_total if pair_total else None,
        "evaluators": reports,
        "review_queue": review_queue,
        "freeform_critiques": critiques,
        "human_completion": human_completion,
        "provenance": capture(),
        "synthetic_demo": any(s.metadata.get("synthetic_demo") for s in submissions),
    }
