"""Small repeated AI annotation pilot. NEVER creates human labels or adjudications."""

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from agent_eval.audit import Contract, audit
from agent_eval.config import load_credentials
from agent_eval.demo import write_json
from agent_eval.evaluators import OpenAIEvaluator
from agent_eval.runner import run
from agent_eval.stability import analyze_repeats
from agent_eval.study import active_imports, ingest, load_study, report, status, subset
from agent_eval.tracing import LangfuseTracer


def verify(tracer, trace_ids, started):
    options = {"timeout_in_seconds": 10, "max_retries": 0}
    now = datetime.now(UTC)
    result = {"expected": len(trace_ids), "observations_verified": 0, "scores_verified": 0}
    try:
        rows = tracer.client.api.observations.get_many(
            name="agent-evaluator-kit",
            fields="core",
            limit=1000,
            from_start_time=started - timedelta(minutes=1),
            to_start_time=now,
            request_options=options,
        )
        found = {r.trace_id for r in rows.data} & trace_ids
        result["observations_verified"] = len(found)
        scores = tracer.client.api.scores_v3.get_many_v3(
            fields="subject",
            limit=100,
            from_timestamp=started - timedelta(minutes=1),
            to_timestamp=now,
            request_options=options,
        )
        score_traces = {
            getattr(s.subject, "trace_id", None)
            or (s.subject.id if getattr(s.subject, "kind", None) == "trace" else None)
            for s in scores.data
            if s.subject is not None
        }
        result["scores_verified"] = len(score_traces & trace_ids)
        result["trace_urls"] = [tracer.client.get_trace_url(trace_id=t) for t in sorted(found)]
    except Exception as exc:
        result.update(error_type=type(exc).__name__, http_status=getattr(exc, "status_code", None))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("study", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--credentials", type=Path)
    parser.add_argument("--langfuse-credentials", type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--max-calls", type=int, default=12)
    parser.add_argument("--contracts", type=Path)
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Read back existing trace IDs; never make model calls",
    )
    args = parser.parse_args()
    if args.verify_only:
        load_credentials(args.langfuse_credentials)
        plan = json.loads((args.output / "plan.json").read_text())
        trace_ids = set()
        for path in args.output.glob("domain-*-pass-*.json"):
            submission = json.loads(path.read_text())
            trace_ids.update(row["trace_id"] for row in submission["metadata"]["traces"])
        verification = verify(
            LangfuseTracer(), trace_ids, datetime.fromisoformat(plan["started_at"])
        )
        write_json(args.output / "trace-verification-followup.json", verification)
        print(json.dumps(verification, indent=2))
        return
    envelope = load_study(args.study)
    manifest = envelope["manifest"]
    before = status(args.study)
    active, _ = active_imports(args.study, envelope)
    existing = {entry["submission"].evaluator_id for entry in active.values()}
    if any(f"ai-luna-{args.run_id}-pass-{repeat}" in existing for repeat in (1, 2)):
        raise ValueError("run ID already imported; choose a new identity before any paid calls")
    bundles = {}
    for domain, criteria in manifest["plan"]["criteria_by_domain"].items():
        ids = {cid for cid, value in manifest["case_domains"].items() if value == domain}
        bundles[domain] = subset(manifest["bundle"], ids, criteria)
    planned = 2 * sum(len(b["cases"]) * len(b["rubric"]["criteria"]) for b in bundles.values())
    if planned > args.max_calls or args.max_calls <= 0:
        raise ValueError("pilot exceeds total call cap; no requests made")
    if args.output.exists():
        raise FileExistsError("choose a fresh output directory")
    load_credentials(args.credentials, args.langfuse_credentials)
    tracer = LangfuseTracer()
    evaluator = OpenAIEvaluator("gpt-6-luna", max_output_tokens=512)
    args.output.mkdir(parents=True)
    started = datetime.now(UTC)
    write_json(
        args.output / "plan.json",
        {
            "study_hash": envelope["study_hash"],
            "model": evaluator.model,
            "planned_evaluations": planned,
            "repeats": 2,
            "max_output_tokens": 512,
            "annotation_origin": "ai_generated",
            "kind": "judge",
            "human_reference_policy": "AI predictions never become human labels",
            "configuration": evaluator.configuration,
            "started_at": started.isoformat(),
        },
    )
    contracts = (
        [Contract.model_validate(c) for c in json.loads(args.contracts.read_text())]
        if args.contracts
        else []
    )
    runs, trace_ids, usage, halted = {}, set(), [], False
    for domain_index, (domain, bundle) in enumerate(sorted(bundles.items()), 1):
        runs[domain] = []
        for repeat in (1, 2):
            if halted:
                break
            identity = f"ai-luna-{args.run_id}-pass-{repeat}"
            submission = run(
                bundle,
                evaluator,
                identity,
                split=manifest["plan"]["split"],
                tracer=tracer,
                max_calls=args.max_calls,
            )
            submission.metadata.update(
                annotation_origin="ai_generated", reference_status="provisional_not_human_validated"
            )
            path = args.output / f"domain-{domain_index:04d}-pass-{repeat}.json"
            write_json(path, submission.model_dump(mode="json"))
            ingest(args.study, path, kind="judge", domain=domain)
            trace_ids.update(r["trace_id"] for r in submission.metadata["traces"])
            usage.extend(submission.metadata["provider_usage"])
            runs[domain].append(submission)
            # Do not continue launching calls after an error in this small paid pilot.
            halted = bool(submission.metadata["errors"])
            print(
                json.dumps(
                    {
                        "domain": domain,
                        "repeat": repeat,
                        "judgments": len(submission.judgments),
                        "errors": len(submission.metadata["errors"]),
                    }
                ),
                flush=True,
            )
    audits, stability = {}, {}
    for domain, submissions in runs.items():
        bundle = bundles[domain]
        cells = {(c["id"], r["id"]) for c in bundle["cases"] for r in bundle["rubric"]["criteria"]}
        selected = [c for c in contracts if (c.case_id, c.criterion_id) in cells]
        if selected:
            audits[domain] = [audit(bundle, s, selected) for s in submissions]
        if len(submissions) == 2:
            stability[domain] = analyze_repeats(bundle, submissions, manifest["plan"]["split"])
    write_json(args.output / "audits.json", audits)
    write_json(args.output / "stability.json", stability)
    verification = verify(tracer, trace_ids, started) if trace_ids else {"expected": 0}
    write_json(args.output / "trace-verification.json", verification)
    after = status(args.study)
    if after["submitted_cells"] != before["submitted_cells"]:
        raise ValueError("human progress changed during pilot; inspect before interpreting results")
    study_report = report(args.study, args.output / "study-report")
    summary = {
        "model": evaluator.model,
        "planned": planned,
        "valid_judgments": sum(len(s.judgments) for ss in runs.values() for s in ss),
        "evaluation_errors": sum(len(s.metadata["errors"]) for ss in runs.values() for s in ss),
        "telemetry_errors": sum(
            len(s.metadata["tracing_errors"]) for ss in runs.values() for s in ss
        ),
        "input_tokens": sum(r["input_tokens"] for r in usage),
        "output_tokens": sum(r["output_tokens"] for r in usage),
        "human_judgments": after["submitted_cells"],
        "human_references_by_domain": {
            d: r["reference_count"] for d, r in study_report["domains"].items()
        },
        "trace_verification": verification,
        "limitation": "Two model passes are not independent human reviewers. "
        "Authored synthetic matches and consistency do not establish human accuracy.",
    }
    write_json(args.output / "summary.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
