import json
from collections import Counter
from datetime import UTC, datetime

import pytest
from typer.testing import CliRunner

from agent_eval import Criterion, EvalCase, Rubric, Submission, bundle_from_cases
from agent_eval.cli import app
from agent_eval.demo import AlwaysPass, write_json
from agent_eval.meta import Judgment
from agent_eval.runner import run
from agent_eval.study import StudyPlan, create_study, ingest, load_study, report, status, subset


def make_inputs(reviewers=None):
    cases, mapping, criteria = [], {}, {}
    for domain in ("analysis", "scheduler", "meeting"):
        criteria[domain] = [domain + "-quality"]
        for group in range(2):
            gid = f"{domain}-{group}"
            mapping[gid] = domain
            for variant in range(2):
                cases.append(
                    EvalCase(
                        id=f"{gid}-{variant}",
                        group_id=gid,
                        split="development",
                        input={"domain": domain, "group": group},
                        output={"value": variant},
                    )
                )
    rubric = Rubric(
        id="quality",
        version="1",
        criteria=[
            Criterion(
                id=ids[0],
                question="Is the output supported?",
                pass_condition="Supported output.",
                fail_condition="Unsupported output.",
            )
            for ids in criteria.values()
        ],
    )
    bundle = bundle_from_cases(cases, rubric)
    plan = StudyPlan(
        id="study",
        version="1",
        purpose="Test calibration",
        split="development",
        reviewers=reviewers or ["alice", "bob"],
        adjudicators=["lead"],
        groups_per_domain=1,
        groups_per_batch=1,
        domain_by_group=mapping,
        criteria_by_domain=criteria,
    )
    return bundle, plan


@pytest.fixture
def study(tmp_path):
    bundle, plan = make_inputs()
    root = tmp_path / "study"
    envelope = create_study(bundle, plan, root)
    return root, envelope


def batch_submission(envelope, batch, *, partial=False):
    bundle = subset(envelope["manifest"]["bundle"], batch["case_ids"], batch["criterion_ids"])
    rows = bundle["cases"][:1] if partial else bundle["cases"]
    return Submission(
        dataset_hash=bundle["dataset_hash"],
        rubric_hash=bundle["rubric_hash"],
        rubric_id=bundle["rubric"]["id"],
        rubric_version=bundle["rubric"]["version"],
        evaluator_id=batch["reviewer"],
        kind="human",
        created_at=datetime.now(UTC),
        judgments=[
            Judgment(
                case_id=c["id"],
                criterion_id=r["id"],
                verdict="pass" if c["output"]["value"] == 0 else "fail",
                rationale="Independent fixture observation.",
            )
            for c in rows
            for r in bundle["rubric"]["criteria"]
        ],
        metadata={
            "study_hash": envelope["study_hash"],
            "batch_id": batch["id"],
            "initial_critiques": {c["id"]: "Initial observation" for c in rows},
            "freeform_critiques": {c["id"]: "Check rubric scope" for c in rows},
        },
    )


def save(tmp_path, submission, name="submission.json"):
    path = tmp_path / name
    write_json(path, submission.model_dump(mode="json"))
    return path


def test_sampling_and_empty_progress(study, tmp_path):
    root, envelope = study
    manifest = envelope["manifest"]
    assert Counter(manifest["case_domains"].values()) == {
        "analysis": 2,
        "meeting": 2,
        "scheduler": 2,
    }
    assert len(manifest["assignments"]) == 6
    for group in manifest["selected_groups"]:
        assignments = [b for b in manifest["assignments"] if group in b["group_ids"]]
        assert {b["reviewer"] for b in assignments} == {"alice", "bob"}
        assert all(len(b["case_ids"]) == 2 for b in assignments)
    result = status(root)
    assert result["submitted_cells"] == 0 and result["possible_cells"] == 12
    output = report(root, tmp_path / "report")
    assert all(
        r["reference_count"] == 0 and len(r["unresolved"]) == 2 for r in output["domains"].values()
    )
    assert output["initial_critiques"] == []


def test_deterministic_assignments(tmp_path):
    bundle, plan = make_inputs(["a", "b", "c"])
    first = create_study(bundle, plan, tmp_path / "one")
    second = create_study(bundle, plan, tmp_path / "two")
    assert first["manifest"]["assignments"] == second["manifest"]["assignments"]
    assert first["manifest"]["selected_groups"] == second["manifest"]["selected_groups"]


@pytest.mark.parametrize("change", ["reviewers", "domain", "criterion", "quota"])
def test_invalid_plan_before_writing(tmp_path, change):
    bundle, plan = make_inputs()
    if change == "reviewers":
        with pytest.raises(ValueError):
            StudyPlan.model_validate({**plan.model_dump(), "reviewers": ["a", "a"]})
        return
    if change == "domain":
        plan.domain_by_group.pop(next(iter(plan.domain_by_group)))
    elif change == "criterion":
        plan.criteria_by_domain["analysis"] = ["unknown"]
    else:
        plan.groups_per_domain = 3
    path = tmp_path / "invalid"
    with pytest.raises(ValueError):
        create_study(bundle, plan, path)
    assert not path.exists()


@pytest.mark.parametrize("target", ["study.json", "rubric.json", "cases.jsonl"])
def test_frozen_inputs(study, target):
    root, _ = study
    path = root / target
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("Supported output", "Changed output"), encoding="utf-8")
    if target == "cases.jsonl":
        path.write_text(text.replace('"value": 0', '"value": 9'), encoding="utf-8")
    with pytest.raises(ValueError):
        load_study(root)


def test_review_page_scope(study):
    root, envelope = study
    batch = envelope["manifest"]["assignments"][0]
    text = (root / "reviews" / (batch["id"] + ".html")).read_text(encoding="utf-8")
    assert "Save initial critique and reveal criteria" in text
    assert batch["reviewer"] in text
    assert "source_blob_hashes" not in text and "expected_verdict" not in text
    data = json.loads(text.split('id="bundle">')[1].split("</script>")[0])
    assert set(c["id"] for c in data["cases"]) == set(batch["case_ids"])
    assert [r["id"] for r in data["rubric"]["criteria"]] == batch["criterion_ids"]
    assert "assignments" not in data and "judgments" not in data


def test_partial_revision_archives_original_bytes(study, tmp_path):
    root, envelope = study
    batch = envelope["manifest"]["assignments"][0]
    source = save(tmp_path, batch_submission(envelope, batch, partial=True))
    raw = source.read_bytes()
    first = ingest(root, source, batch_id=batch["id"])
    assert (root / "imports" / (first["blob_hash"] + ".json")).read_bytes() == raw
    assert status(root)["submitted_cells"] == 1
    assert ingest(root, source, batch_id=batch["id"])["status"] == "already_imported"
    revised = save(tmp_path, batch_submission(envelope, batch), "revised.json")
    with pytest.raises(ValueError, match="replacement"):
        ingest(root, revised, batch_id=batch["id"])
    second = ingest(root, revised, batch_id=batch["id"], replace=True)
    assert second["replaces"] == first["blob_hash"]
    assert len(list((root / "imports").glob("*.json"))) == 2
    assert status(root)["submitted_cells"] == 2
    assert status(root)["complete_batches"] == 1


@pytest.mark.parametrize("problem", ["reviewer", "hash", "metadata", "synthetic", "notes", "case"])
def test_bad_human_import_rejected(study, tmp_path, problem):
    root, envelope = study
    batch = envelope["manifest"]["assignments"][0]
    submission = batch_submission(envelope, batch)
    if problem == "reviewer":
        submission.evaluator_id = "outsider"
    elif problem == "hash":
        submission.rubric_hash = "wrong"
    elif problem == "metadata":
        submission.metadata.pop("study_hash")
    elif problem == "synthetic":
        submission.metadata["synthetic_demo"] = True
    elif problem == "notes":
        submission.metadata["initial_critiques"]["unknown"] = "extra"
    else:
        submission.judgments[0].case_id = "unknown"
    with pytest.raises(ValueError):
        ingest(root, save(tmp_path, submission), batch_id=batch["id"])
    assert not list((root / "events").glob("*.json"))


def test_domain_judge_human_consensus_and_disagreement(study, tmp_path):
    root, envelope = study
    manifest = envelope["manifest"]
    batches = [b for b in manifest["assignments"] if b["domain"] == "analysis"]
    for index, batch in enumerate(batches):
        submission = batch_submission(envelope, batch)
        ingest(root, save(tmp_path, submission, f"human-{index}.json"), batch_id=batch["id"])
    domain_bundle = subset(manifest["bundle"], batches[0]["case_ids"], batches[0]["criterion_ids"])
    judge = run(domain_bundle, AlwaysPass(), "judge", split="development")
    ingest(root, save(tmp_path, judge, "judge.json"), kind="judge", domain="analysis")
    result = report(root, tmp_path / "consensus")
    assert result["domains"]["analysis"]["reference_count"] == 2
    assert result["domains"]["analysis"]["evaluators"]["judge"]["all"]["fn"] == 1
    assert result["domains"]["meeting"]["reference_count"] == 0
    assert len(result["initial_critiques"]) == 4
    changed = batch_submission(envelope, batches[1])
    changed.judgments[0].verdict = "fail" if changed.judgments[0].verdict == "pass" else "pass"
    ingest(root, save(tmp_path, changed, "changed.json"), batch_id=batches[1]["id"], replace=True)
    result = report(root, tmp_path / "disagreement")
    assert result["domains"]["analysis"]["reference_count"] == 1
    assert len(result["domains"]["analysis"]["unresolved"]) == 1
    adjudication = judge.model_copy(deep=True)
    adjudication.kind, adjudication.evaluator_id = "adjudication", "lead"
    adjudication.metadata["adjudication_reason"] = "Reviewed both annotations and source evidence"
    ingest(
        root,
        save(tmp_path, adjudication, "adjudicated.json"),
        kind="adjudication",
        domain="analysis",
    )
    assert report(root, tmp_path / "adjudicated")["domains"]["analysis"]["reference_count"] == 2


def test_import_tampering(study, tmp_path):
    root, envelope = study
    batch = envelope["manifest"]["assignments"][0]
    event = ingest(root, save(tmp_path, batch_submission(envelope, batch)), batch_id=batch["id"])
    path = root / "imports" / (event["blob_hash"] + ".json")
    with path.open("ab") as stream:
        stream.write(b" ")
    with pytest.raises(ValueError, match="bytes changed"):
        status(root)


def test_adjudicator_and_applicability(study, tmp_path):
    root, envelope = study
    bundle = envelope["manifest"]["bundle"]
    judge = run(bundle, AlwaysPass(), "all-dimensions", split="development")
    with pytest.raises(ValueError, match="outside its case domain"):
        ingest(root, save(tmp_path, judge, "judge.json"), kind="judge")
    judge.kind, judge.evaluator_id = "adjudication", "unregistered"
    with pytest.raises(ValueError, match="unregistered"):
        ingest(root, save(tmp_path, judge, "adjudication.json"), kind="adjudication")


def test_cli_demo_has_no_human_labels(tmp_path):
    output = tmp_path / "demo"
    result = CliRunner().invoke(app, ["study", "demo", str(output)])
    assert result.exit_code == 0, result.output
    data = json.loads((output / "initial-report/report.json").read_text(encoding="utf-8"))
    assert data["progress"]["submitted_cells"] == 0
    assert all(r["reference_count"] == 0 for r in data["domains"].values())


def test_three_required_human_votes(tmp_path):
    bundle, plan = make_inputs(["a", "b", "c"])
    plan.reviews_per_group = 3
    root = tmp_path / "study"
    envelope = create_study(bundle, plan, root)
    batches = [b for b in envelope["manifest"]["assignments"] if b["domain"] == "analysis"]
    for i, batch in enumerate(batches[:2]):
        ingest(
            root,
            save(tmp_path, batch_submission(envelope, batch), f"r-{i}.json"),
            batch_id=batch["id"],
        )
    assert report(root, tmp_path / "two")["domains"]["analysis"]["reference_count"] == 0
    batch = batches[2]
    ingest(root, save(tmp_path, batch_submission(envelope, batch)), batch_id=batch["id"])
    assert report(root, tmp_path / "three")["domains"]["analysis"]["reference_count"] == 2


def test_adjudication_reason_and_identity(study, tmp_path):
    root, envelope = study
    batch = envelope["manifest"]["assignments"][0]
    bundle = subset(envelope["manifest"]["bundle"], batch["case_ids"], batch["criterion_ids"])
    submission = run(bundle, AlwaysPass(), "lead", split="development")
    with pytest.raises(ValueError, match="distinct"):
        ingest(root, save(tmp_path, submission, "judge.json"), kind="judge", domain=batch["domain"])
    submission.kind = "adjudication"
    with pytest.raises(ValueError, match="explicit reason"):
        ingest(
            root,
            save(tmp_path, submission, "adjudication.json"),
            kind="adjudication",
            domain=batch["domain"],
        )


def test_missing_initial_notes_not_complete(study, tmp_path):
    root, envelope = study
    batch = envelope["manifest"]["assignments"][0]
    submission = batch_submission(envelope, batch)
    submission.metadata["initial_critiques"] = {}
    ingest(root, save(tmp_path, submission), batch_id=batch["id"])
    assert status(root)["submitted_cells"] == 2
    assert status(root)["complete_batches"] == 0


def test_trace_provenance_and_critique_escaping(study, tmp_path):
    root, envelope = study
    batch = envelope["manifest"]["assignments"][0]
    submission = batch_submission(envelope, batch)
    submission.metadata["initial_critiques"][batch["case_ids"][0]] = "</pre><script>bad()</script>"
    ingest(root, save(tmp_path, submission), batch_id=batch["id"])
    bundle = subset(envelope["manifest"]["bundle"], batch["case_ids"], batch["criterion_ids"])
    judge = run(bundle, AlwaysPass(), "judge", split="development")
    judge.metadata["provider_usage"] = [
        {"input_tokens": 11, "output_tokens": 3, "total_tokens": 14}
    ]
    judge.metadata["traces"] = [{"trace_id": "trace-example"}]
    ingest(root, save(tmp_path, judge, "judge.json"), kind="judge", domain=batch["domain"])
    result = report(root, tmp_path / "report")
    assert result["judge_runs"][0]["reported_tokens"]["total_tokens"] == 14
    assert result["judge_runs"][0]["traces"][0]["trace_id"] == "trace-example"
    text = (tmp_path / "report/index.html").read_text(encoding="utf-8")
    assert "<script>bad()" not in text and "&lt;script&gt;bad()" in text


def test_history_and_import_lock(study, tmp_path):
    root, envelope = study
    batch = envelope["manifest"]["assignments"][0]
    path = save(tmp_path, batch_submission(envelope, batch))
    (root / ".import.lock").touch()
    with pytest.raises(FileExistsError):
        ingest(root, path, batch_id=batch["id"])
    assert not list((root / "events").glob("*.json"))


def test_no_overwrite(study, tmp_path):
    root, _ = study
    bundle, plan = make_inputs()
    with pytest.raises(FileExistsError):
        create_study(bundle, plan, root)
    report(root, tmp_path / "report")
    with pytest.raises(FileExistsError):
        report(root, tmp_path / "report")


@pytest.mark.parametrize("origin", ["ai_generated", "automated_evaluator"])
def test_automated_annotation_cannot_be_relabelled_human(study, tmp_path, origin):
    root, envelope = study
    batch = envelope["manifest"]["assignments"][0]
    submission = batch_submission(envelope, batch)
    submission.metadata["annotation_origin"] = origin
    with pytest.raises(ValueError, match="cannot be imported as human"):
        ingest(root, save(tmp_path, submission), batch_id=batch["id"])
    assert status(root)["submitted_cells"] == 0


def test_paid_pilot_checks_total_cap_before_provider_setup(study, tmp_path, monkeypatch):
    import importlib.util
    import sys
    from pathlib import Path

    script = Path(__file__).resolve().parents[1] / "scripts/run_ai_annotation_pilot.py"
    spec = importlib.util.spec_from_file_location("pilot_test", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def forbidden(*args, **kwargs):
        raise AssertionError("provider setup must not happen")

    monkeypatch.setattr(module, "LangfuseTracer", forbidden)
    monkeypatch.setattr(module, "OpenAIEvaluator", forbidden)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(script),
            str(study[0]),
            str(tmp_path / "pilot"),
            "--run-id",
            "cap-check",
            "--max-calls",
            "1",
        ],
    )
    with pytest.raises(ValueError, match="total call cap"):
        module.main()
    assert not (tmp_path / "pilot").exists()
