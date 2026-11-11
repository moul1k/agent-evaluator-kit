"""Commands for studies; no API calls or automatic human labels."""

import json
from pathlib import Path

import typer

from .demo import demo, write_json
from .meta import load_bundle
from .study import StudyPlan, create_study, ingest, report, status

app = typer.Typer(no_args_is_help=True, help="Frozen review studies and evaluator comparisons.")


@app.command("create")
def create(cases: Path, rubric: Path, plan: Path, output: Path):
    """Freeze a protocol and sample complete groups, balanced by domain."""
    result = create_study(
        load_bundle(cases, rubric),
        StudyPlan.model_validate_json(plan.read_text(encoding="utf-8")),
        output,
    )
    typer.echo(
        json.dumps(
            {"study_hash": result["study_hash"], "batches": len(result["manifest"]["assignments"])},
            indent=2,
        )
    )


@app.command("status")
def show_status(study: Path, output: Path | None = None):
    result = status(study)
    if output:
        write_json(output, result)
    typer.echo(json.dumps(result, indent=2))


@app.command("ingest-human")
def ingest_human(study: Path, batch_id: str, submission: Path, replace: bool = False):
    typer.echo(json.dumps(ingest(study, submission, batch_id=batch_id, replace=replace), indent=2))


@app.command("add-judge")
def add_judge(study: Path, submission: Path, domain: str | None = None, replace: bool = False):
    typer.echo(
        json.dumps(
            ingest(study, submission, kind="judge", domain=domain, replace=replace), indent=2
        )
    )


@app.command("adjudicate")
def adjudicate(study: Path, submission: Path, domain: str | None = None, replace: bool = False):
    typer.echo(
        json.dumps(
            ingest(study, submission, kind="adjudication", domain=domain, replace=replace), indent=2
        )
    )


@app.command("report")
def build_report(study: Path, output: Path):
    result = report(study, output)
    typer.echo(
        json.dumps(
            {
                "study_hash": result["study_hash"],
                "complete_batches": result["progress"]["complete_batches"],
                "references_by_domain": {
                    name: row["reference_count"] for name, row in result["domains"].items()
                },
            },
            indent=2,
        )
    )


@app.command("demo")
def study_demo(output: Path):
    """Create a synthetic study with EMPTY human labels, ready for manual review."""
    output.mkdir(parents=True, exist_ok=False)
    demo(output / "fixtures")
    bundle = load_bundle(output / "fixtures/cases.jsonl", output / "fixtures/rubric.json")
    plan = StudyPlan(
        id="synthetic-calibration-demo",
        version="1",
        split="test",
        purpose="Demonstrate review workflow, not measured human accuracy.",
        reviewers=["reviewer-a", "reviewer-b"],
        adjudicators=["study-lead"],
        groups_per_domain=1,
        groups_per_batch=1,
        domain_by_group={name: name for name in ("analysis", "scheduler", "meeting")},
        criteria_by_domain={
            name: ["numerical_evidence"] for name in ("analysis", "scheduler", "meeting")
        },
    )
    write_json(output / "plan.json", plan.model_dump())
    create_study(bundle, plan, output / "study")
    result = report(output / "study", output / "initial-report")
    typer.echo(
        json.dumps(
            {
                "review_pages": result["progress"]["total_batches"],
                "human_judgments": result["progress"]["submitted_cells"],
                "report": str(output / "initial-report/index.html"),
            },
            indent=2,
        )
    )
