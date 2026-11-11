"""Frozen study planning, blind review assignments, and auditable label collection.

Study hashes detect accidental changes, not a malicious organizer. Reviewer identity
and independence are organizational controls; this offline workflow has no authentication.
"""

import json
import math
import random
import statistics
from collections import defaultdict
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from .demo import write_json
from .meta import Rubric, Submission, bundle_from_cases, compare, digest, validate_submission
from .reporting import write_html
from .review import export_review
from .schemas import StrictModel


class StudyPlan(StrictModel):
    id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    split: Literal["discovery", "development", "test"] = "development"
    reviewers: list[str] = Field(min_length=2)
    adjudicators: list[str] = Field(default_factory=list)
    reviews_per_group: int = Field(default=2, ge=2)
    groups_per_domain: int = Field(default=15, ge=1)
    groups_per_batch: int = Field(default=5, ge=1)
    seed: int = 42
    domain_by_group: dict[str, str]
    criteria_by_domain: dict[str, list[str]]

    @model_validator(mode="after")
    def valid(self):
        for names in (self.reviewers, self.adjudicators):
            if len(set(names)) != len(names) or any(not name.strip() for name in names):
                raise ValueError("reviewer/adjudicator identities must be unique and nonblank")
        if set(self.reviewers) & set(self.adjudicators):
            raise ValueError("use separate reviewer and adjudicator identities")
        if self.reviews_per_group > len(self.reviewers):
            raise ValueError("not enough independent reviewer identities")
        if not self.criteria_by_domain or any(not name.strip() for name in self.criteria_by_domain):
            raise ValueError("nonempty domain names required")
        for criteria in self.criteria_by_domain.values():
            if not criteria or len(set(criteria)) != len(criteria):
                raise ValueError("each domain needs nonempty unique criterion IDs")
        return self


def subset(bundle, case_ids, criterion_ids):
    rubric = Rubric.model_validate(bundle["rubric"])
    rubric.criteria = [r for r in rubric.criteria if r.id in criterion_ids]
    rows = [c for c in bundle["cases"] if c["id"] in case_ids]
    if isinstance(case_ids, list):
        lookup = {c["id"]: c for c in rows}
        rows = [lookup[cid] for cid in case_ids]
    return bundle_from_cases(rows, rubric)


def create_study(bundle: dict, plan: StudyPlan, output: Path):
    plan = StudyPlan.model_validate(plan.model_dump())
    # Rebuild instead of trusting a caller-provided hash or unvalidated bundle.
    source = bundle_from_cases(bundle["cases"], Rubric.model_validate(bundle["rubric"]))
    criterion_ids = {r["id"] for r in source["rubric"]["criteria"]}
    if any(not set(ids) <= criterion_ids for ids in plan.criteria_by_domain.values()):
        raise ValueError("domain references an unknown criterion")
    all_groups = {c["group_id"] for c in source["cases"]}
    if set(plan.domain_by_group) - all_groups:
        raise ValueError("domain mapping references unknown groups")
    groups = defaultdict(list)
    for group in sorted({c["group_id"] for c in source["cases"] if c["split"] == plan.split}):
        domain = plan.domain_by_group.get(group)
        if domain not in plan.criteria_by_domain:
            raise ValueError("every group in the selected split needs a configured domain")
        groups[domain].append(group)
    if set(groups) != set(plan.criteria_by_domain):
        raise ValueError("configured domains must all have eligible groups")
    rng = random.Random(plan.seed)
    selected, assignments, case_domains = [], [], {}
    workloads = {r: 0 for r in plan.reviewers}
    for domain in sorted(groups):
        candidates = groups[domain]
        if len(candidates) < plan.groups_per_domain:
            raise ValueError(
                f"domain {domain} has insufficient source groups; no downsampling fallback"
            )
        rng.shuffle(candidates)
        chosen = candidates[: plan.groups_per_domain]
        selected.extend(chosen)
        per_reviewer = defaultdict(list)
        for group in chosen:
            rows = [c for c in source["cases"] if c["group_id"] == group]
            for row in rows:
                case_domains[row["id"]] = domain
            # Balance criterion-cell workload, keeping every group's variants together.
            order = plan.reviewers.copy()
            rng.shuffle(order)
            order.sort(key=lambda name: workloads[name])
            for reviewer in order[: plan.reviews_per_group]:
                per_reviewer[reviewer].append(group)
                workloads[reviewer] += len(rows) * len(plan.criteria_by_domain[domain])
        for reviewer in sorted(per_reviewer):
            assigned = per_reviewer[reviewer]
            for start in range(0, len(assigned), plan.groups_per_batch):
                batch_groups = assigned[start : start + plan.groups_per_batch]
                ids = [c["id"] for c in source["cases"] if c["group_id"] in batch_groups]
                rng.shuffle(ids)
                assignments.append(
                    {
                        "id": f"batch-{len(assignments) + 1:04d}",
                        "reviewer": reviewer,
                        "domain": domain,
                        "group_ids": batch_groups,
                        "case_ids": ids,
                        "criterion_ids": plan.criteria_by_domain[domain],
                    }
                )
    frozen = bundle_from_cases(
        [c for c in source["cases"] if c["group_id"] in selected],
        Rubric.model_validate(source["rubric"]),
    )
    manifest = {
        "schema_version": "1",
        "plan": plan.model_dump(),
        "bundle": frozen,
        "source_dataset_hash": source["dataset_hash"],
        "selected_groups": selected,
        "case_domains": case_domains,
        "assignments": assignments,
        "created_at": datetime.now(UTC).isoformat(),
    }
    envelope = {"manifest": manifest, "study_hash": digest(manifest)}
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "study.json", envelope)
    write_json(output / "rubric.json", frozen["rubric"])
    with (output / "cases.jsonl").open("x", encoding="utf-8") as stream:
        for case in frozen["cases"]:
            stream.write(json.dumps(case) + "\n")
    for name in ("reviews", "imports", "events"):
        (output / name).mkdir()
    (output / "domains").mkdir()
    for i, (domain, ids) in enumerate(sorted(plan.criteria_by_domain.items()), 1):
        domain_bundle = subset(
            frozen, {cid for cid, name in case_domains.items() if name == domain}, ids
        )
        directory = output / "domains" / f"domain-{i:04d}"
        directory.mkdir()
        write_json(
            directory / "domain.json", {"domain": domain, "study_hash": envelope["study_hash"]}
        )
        write_json(directory / "rubric.json", domain_bundle["rubric"])
        with (directory / "cases.jsonl").open("x", encoding="utf-8") as stream:
            for case in domain_bundle["cases"]:
                stream.write(json.dumps(case) + "\n")
    for assignment in assignments:
        review = subset(frozen, assignment["case_ids"], assignment["criterion_ids"])
        export_review(
            review,
            output / "reviews" / (assignment["id"] + ".html"),
            context={
                "study_hash": envelope["study_hash"],
                "batch_id": assignment["id"],
                "reviewer_id": assignment["reviewer"],
                "critique_first": True,
            },
        )
    return envelope


def load_study(root: Path):
    envelope = json.loads((root / "study.json").read_text(encoding="utf-8"))
    manifest = envelope["manifest"]
    if digest(manifest) != envelope["study_hash"]:
        raise ValueError("frozen study manifest changed")
    StudyPlan.model_validate(manifest["plan"])
    normalized = bundle_from_cases(
        manifest["bundle"]["cases"], Rubric.model_validate(manifest["bundle"]["rubric"])
    )
    if normalized != manifest["bundle"]:
        raise ValueError("study bundle provenance mismatch")
    # Convenience exports are part of the frozen study, not editable inputs.
    from .meta import load_bundle

    if load_bundle(root / "cases.jsonl", root / "rubric.json") != normalized:
        raise ValueError("frozen case or rubric exports changed")
    return envelope


@contextmanager
def study_lock(root):
    path = root / ".import.lock"
    stream = path.open("x", encoding="utf-8")
    try:
        yield
    finally:
        stream.close()
        path.unlink()


def active_imports(root, envelope):
    active = {}
    previous = None
    for number, path in enumerate(sorted((root / "events").glob("*.json")), 1):
        event = json.loads(path.read_text(encoding="utf-8"))
        if (
            path.name != f"{number:06d}.json"
            or event["sequence"] != number
            or event["study_hash"] != envelope["study_hash"]
            or event["previous_event_hash"] != previous
        ):
            raise ValueError("import event history is inconsistent")
        blob = event["blob_hash"]
        if len(blob) != 64 or any(c not in "0123456789abcdef" for c in blob):
            raise ValueError("invalid archived submission hash")
        raw = (root / "imports" / (blob + ".json")).read_bytes()
        import hashlib

        if hashlib.sha256(raw).hexdigest() != blob:
            raise ValueError("archived submission bytes changed")
        submission = Submission.model_validate_json(raw)
        validate_import(envelope, event["kind"], event["batch_id"], submission, event["domain"])
        key = (event["kind"], event["batch_id"] or submission.evaluator_id, event["domain"])
        if event["replaces"] != (active[key]["blob_hash"] if key in active else None):
            raise ValueError("import replacement history is inconsistent")
        active[key] = {**event, "submission": submission}
        previous = digest(event)
    return active, previous


def validate_import(envelope, kind, batch_id, submission, domain=None):
    manifest = envelope["manifest"]
    plan = manifest["plan"]
    if submission.kind != kind:
        raise ValueError("wrong submission kind")
    if any(not j.rationale.strip() for j in submission.judgments):
        raise ValueError("every judgment needs a nonblank rationale")
    for field in ("timings", "provider_usage", "traces"):
        if field in submission.metadata and not isinstance(submission.metadata[field], list):
            raise ValueError("runtime metadata collections must be lists")
    if submission.metadata.get("synthetic_demo"):
        raise ValueError("scripted demo labels cannot enter a human study")
    if kind == "human":
        if submission.metadata.get("annotation_origin") in ("ai_generated", "automated_evaluator"):
            raise ValueError("automated predictions cannot be imported as human annotations")
        if domain is not None:
            raise ValueError("human import uses batch identity, not a domain override")
        batches = [b for b in manifest["assignments"] if b["id"] == batch_id]
        if not batches or submission.evaluator_id != batches[0]["reviewer"]:
            raise ValueError("unknown batch or wrong assigned reviewer")
        batch = batches[0]
        validate_submission(
            submission, subset(manifest["bundle"], batch["case_ids"], batch["criterion_ids"])
        )
        if (
            submission.metadata.get("study_hash") != envelope["study_hash"]
            or submission.metadata.get("batch_id") != batch_id
        ):
            raise ValueError("study/batch metadata missing or mismatched")
        for key in ("freeform_critiques", "initial_critiques"):
            notes = submission.metadata.get(key, {})
            if (
                not isinstance(notes, dict)
                or not set(notes) <= set(batch["case_ids"])
                or any(not isinstance(v, str) for v in notes.values())
            ):
                raise ValueError("critique metadata must reference assigned cases only")
    else:
        if batch_id is not None:
            raise ValueError("nonhuman submissions do not belong to review batches")
        target = manifest["bundle"]
        if domain is not None:
            if domain not in plan["criteria_by_domain"]:
                raise ValueError("unknown study domain")
            target = subset(
                target,
                {cid for cid, name in manifest["case_domains"].items() if name == domain},
                plan["criteria_by_domain"][domain],
            )
        validate_submission(submission, target)
        if kind == "judge" and submission.evaluator_id in plan["reviewers"] + plan["adjudicators"]:
            raise ValueError("human and judge identities must be distinct")
        if kind == "adjudication":
            if submission.evaluator_id not in plan["adjudicators"]:
                raise ValueError("unregistered adjudicator")
            reason = submission.metadata.get("adjudication_reason", "")
            if not isinstance(reason, str) or not reason.strip():
                raise ValueError("adjudication needs an explicit reason")
        allowed = {
            (c["id"], r)
            for c in manifest["bundle"]["cases"]
            for r in plan["criteria_by_domain"][manifest["case_domains"][c["id"]]]
        }
        if any((j.case_id, j.criterion_id) not in allowed for j in submission.judgments):
            raise ValueError("judgment uses a criterion outside its case domain")


def ingest(root: Path, source: Path, *, kind="human", batch_id=None, domain=None, replace=False):
    import hashlib

    envelope = load_study(root)
    raw = source.read_bytes()
    submission = Submission.model_validate_json(raw)
    validate_import(envelope, kind, batch_id, submission, domain)
    blob_hash = hashlib.sha256(raw).hexdigest()
    with study_lock(root):
        active, previous = active_imports(root, envelope)
        key = (kind, batch_id or submission.evaluator_id, domain)
        if kind != "human":
            for other_kind, other_identity, other_domain in active:
                if (
                    other_kind == kind
                    and other_identity == submission.evaluator_id
                    and (other_domain is None) != (domain is None)
                ):
                    raise ValueError(
                        "cannot mix whole-study and per-domain snapshots for one identity"
                    )
        old = active.get(key)
        if old and old["blob_hash"] == blob_hash:
            return {"status": "already_imported", "blob_hash": blob_hash}
        if old and not replace:
            raise ValueError(
                "active submission exists; use explicit replacement for a revised snapshot"
            )
        archived = root / "imports" / (blob_hash + ".json")
        if not archived.exists():
            with archived.open("xb") as stream:
                stream.write(raw)
        elif archived.read_bytes() != raw:
            raise ValueError("existing archived bytes do not match the source export")
        sequence = len(list((root / "events").glob("*.json"))) + 1
        event = {
            "sequence": sequence,
            "kind": kind,
            "batch_id": batch_id,
            "domain": domain,
            "blob_hash": blob_hash,
            "study_hash": envelope["study_hash"],
            "previous_event_hash": previous,
            "replaces": old["blob_hash"] if old else None,
            "imported_at": datetime.now(UTC).isoformat(),
        }
        # Publish an entire event at once so a concurrent read never sees partial JSON.
        destination = root / "events" / f"{sequence:06d}.json"
        pending = destination.with_suffix(".pending")
        write_json(pending, event)
        if destination.exists():
            raise ValueError("event sequence unexpectedly exists")
        pending.replace(destination)
    return {"status": "imported", **event}


def status(root: Path):
    envelope = load_study(root)
    active, _ = active_imports(root, envelope)
    batches = []
    for batch in envelope["manifest"]["assignments"]:
        entry = active.get(("human", batch["id"], None))
        submission = entry["submission"] if entry else None
        possible = len(batch["case_ids"]) * len(batch["criterion_ids"])
        count = len(submission.judgments) if submission else 0
        notes = submission.metadata.get("initial_critiques", {}) if submission else {}
        initial = sum(bool(notes.get(cid, "").strip()) for cid in batch["case_ids"])
        batches.append(
            {
                **batch,
                "possible_cells": possible,
                "submitted_cells": count,
                "initial_critiques": initial,
                "possible_critiques": len(batch["case_ids"]),
                "complete": count == possible and initial == len(batch["case_ids"]),
            }
        )
    return {
        "study_hash": envelope["study_hash"],
        "batches": batches,
        "complete_batches": sum(b["complete"] for b in batches),
        "total_batches": len(batches),
        "submitted_cells": sum(b["submitted_cells"] for b in batches),
        "possible_cells": sum(b["possible_cells"] for b in batches),
    }


def canonical_submissions(envelope, active):
    """Controlled normalization retains archived source hashes; never edit raw exports."""
    frozen = envelope["manifest"]["bundle"]
    grouped = defaultdict(list)
    for entry in active.values():
        submission = entry["submission"]
        grouped[submission.kind, submission.evaluator_id].append(entry)
    result = []
    for (kind, identity), entries in grouped.items():
        judgments, initial, critiques = [], {}, {}
        for entry in entries:
            submission = entry["submission"]
            judgments.extend(submission.judgments)
            if kind == "human":
                initial.update(submission.metadata.get("initial_critiques", {}))
                critiques.update(submission.metadata.get("freeform_critiques", {}))
        result.append(
            Submission(
                dataset_hash=frozen["dataset_hash"],
                rubric_hash=frozen["rubric_hash"],
                rubric_id=frozen["rubric"]["id"],
                rubric_version=frozen["rubric"]["version"],
                evaluator_id=identity,
                kind=kind,
                created_at=max(e["submission"].created_at for e in entries),
                judgments=judgments,
                metadata={
                    "study_hash": envelope["study_hash"],
                    "source_blob_hashes": [e["blob_hash"] for e in entries],
                    "initial_critiques": initial,
                    "freeform_critiques": critiques,
                },
            )
        )
    return result


def report(root: Path, output: Path):
    envelope = load_study(root)
    active, _ = active_imports(root, envelope)
    submissions = canonical_submissions(envelope, active)
    manifest, reports = envelope["manifest"], {}
    for domain, criterion_ids in manifest["plan"]["criteria_by_domain"].items():
        ids = {cid for cid, name in manifest["case_domains"].items() if name == domain}
        domain_bundle = subset(manifest["bundle"], ids, criterion_ids)
        domain_submissions = []
        for submission in submissions:
            data = submission.model_dump(mode="json")
            data.update({key: domain_bundle[key] for key in ("dataset_hash", "rubric_hash")})
            data["judgments"] = [
                j
                for j in data["judgments"]
                if j["case_id"] in ids and j["criterion_id"] in criterion_ids
            ]
            domain_submissions.append(Submission.model_validate(data))
        reports[domain] = compare(
            domain_bundle,
            domain_submissions,
            manifest["plan"]["split"],
            minimum_human_votes=manifest["plan"]["reviews_per_group"],
        )
    progress = status(root)
    judge_runs = []
    for entry in active.values():
        submission = entry["submission"]
        if submission.kind != "judge":
            continue
        metadata = submission.metadata
        timings = [
            r["latency_ms"]
            for r in metadata.get("timings", [])
            if isinstance(r, dict)
            and isinstance(r.get("latency_ms"), (float, int))
            and math.isfinite(r["latency_ms"])
            and r["latency_ms"] >= 0
        ]
        usage = metadata.get("provider_usage", [])
        tokens = {}
        for key in ("input_tokens", "output_tokens", "total_tokens"):
            values = [
                r[key]
                for r in usage
                if isinstance(r, dict)
                and isinstance(r.get(key), int)
                and not isinstance(r.get(key), bool)
                and r[key] >= 0
            ]
            tokens[key] = sum(values) if values else None
        judge_runs.append(
            {
                "evaluator_id": submission.evaluator_id,
                "domain": entry["domain"],
                "annotation_origin": metadata.get("annotation_origin", "not_reported"),
                "source_blob_hash": entry["blob_hash"],
                "configuration_hash": metadata.get("configuration_hash"),
                "reported_timing_count": len(timings),
                "median_latency_ms": statistics.median(timings) if timings else None,
                "reported_tokens": tokens,
                "token_usage_available": any(value is not None for value in tokens.values()),
                "traces": metadata.get("traces", []),
            }
        )
    results = {
        "study_hash": envelope["study_hash"],
        "plan": manifest["plan"],
        "reference_type": "independent_human_consensus_or_registered_adjudication",
        "progress": progress,
        "domains": reports,
        "judge_runs": judge_runs,
        "initial_critiques": [
            {"reviewer": s.evaluator_id, "case_id": cid, "critique": text}
            for s in submissions
            if s.kind == "human"
            for cid, text in s.metadata["initial_critiques"].items()
        ],
        "limitation": "Identity is not authenticated. No pooled cross-domain accuracy. "
        "Freeform rubric concerns require human analysis, not automatic truth.",
    }
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "report.json", results)
    for i, (domain, domain_report) in enumerate(sorted(reports.items()), 1):
        write_html(domain_report, output / f"domain-{i:04d}.html")
    from .study_report import write_index

    write_index(results, output / "index.html")
    return results
