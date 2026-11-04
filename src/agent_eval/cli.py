"""CLI uses the same public API as embedded deployments."""

import json
from pathlib import Path

import typer

from .adapters import data_analysis, scheduler, transcription
from .audit import Contract, audit
from .demo import demo as make_demo
from .demo import write_json
from .evaluators import NumericResultEvaluator, OpenAIEvaluator, SubprocessEvaluator
from .meta import Submission, compare, load_bundle, validate_submission
from .reporting import write_html
from .review import export_review
from .runner import run as execute
from .scheduling import ScheduleConstraintEvaluator
from .schemas import EvalCase
from .stability import analyze_repeats
from .tracing import LangfuseTracer

app = typer.Typer(no_args_is_help=True)


@app.command()
def demo(output: Path, langfuse: bool = False):
    """Free synthetic demo; cloud traces only with --langfuse."""
    reports = make_demo(output, LangfuseTracer() if langfuse else None)
    typer.echo(
        json.dumps(
            {
                k: {"match_rate": v["match_rate"], "false_acceptances": v["false_acceptances"]}
                for k, v in reports.items()
            },
            indent=2,
        )
    )


@app.command()
def prepare(cases: Path, rubric: Path, output: Path):
    bundle = load_bundle(cases, rubric)
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "bundle.json", bundle)
    export_review(bundle, output / "review.html")
    write_json(output / "case.schema.json", EvalCase.model_json_schema())
    write_json(output / "submission.schema.json", Submission.model_json_schema())


@app.command("run")
def run_command(
    cases: Path,
    rubric: Path,
    output: Path,
    evaluator_id: str,
    plugin: str = "numeric",
    model: str = "",
    command_json: str = "[]",
    split: str = "test",
    langfuse: bool = False,
    trace_content: bool = False,
):
    if output.exists():
        raise typer.BadParameter("output already exists")
    if trace_content and not langfuse:
        raise typer.BadParameter("--trace-content requires --langfuse")
    if plugin == "numeric":
        evaluator = NumericResultEvaluator()
    elif plugin == "schedule":
        evaluator = ScheduleConstraintEvaluator()
    elif plugin == "openai" and model:
        evaluator = OpenAIEvaluator(model)
    elif plugin == "subprocess":
        command = json.loads(command_json)
        if not isinstance(command, list) or not all(isinstance(v, str) for v in command):
            raise typer.BadParameter("command-json must be a string array")
        evaluator = SubprocessEvaluator(command)
    else:
        raise typer.BadParameter("use numeric, schedule, subprocess, or openai with --model")
    result = execute(
        load_bundle(cases, rubric),
        evaluator,
        evaluator_id,
        split,
        LangfuseTracer(include_content=trace_content) if langfuse else None,
        configuration={"plugin": plugin, "model": model, "command": json.loads(command_json)},
    )
    write_json(output, result.model_dump(mode="json"))
    if result.metadata["errors"] or result.metadata["tracing_errors"]:
        raise typer.Exit(1)


@app.command()
def validate(cases: Path, rubric: Path, submission: Path):
    validate_submission(
        Submission.model_validate_json(submission.read_text(encoding="utf-8")),
        load_bundle(cases, rubric),
    )
    typer.echo("Valid submission and provenance")


@app.command("compare")
def compare_command(
    cases: Path, rubric: Path, submissions: Path, output: Path, split: str = "test"
):
    values = [
        Submission.model_validate_json(p.read_text(encoding="utf-8"))
        for p in sorted(submissions.glob("*.json"))
    ]
    report = compare(load_bundle(cases, rubric), values, split)
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "report.json", report)
    write_html(report, output / "report.html")


@app.command()
def repeats(cases: Path, rubric: Path, submissions: Path, output: Path, split: str = "test"):
    values = [
        Submission.model_validate_json(p.read_text(encoding="utf-8"))
        for p in sorted(submissions.glob("*.json"))
    ]
    write_json(output, analyze_repeats(load_bundle(cases, rubric), values, split))


@app.command("audit")
def audit_command(
    cases: Path,
    rubric: Path,
    submission: Path,
    contracts: Path,
    output: Path,
    minimum_match: float = 0.95,
    maximum_false_acceptances: int = 0,
):
    if not 0 <= minimum_match <= 1 or maximum_false_acceptances < 0:
        raise typer.BadParameter("invalid gate thresholds")
    report = audit(
        load_bundle(cases, rubric),
        Submission.model_validate_json(submission.read_text(encoding="utf-8")),
        [Contract.model_validate(c) for c in json.loads(contracts.read_text(encoding="utf-8"))],
    )
    write_json(output, report)
    if (
        report["match_rate"] < minimum_match
        or report["false_acceptances"] > maximum_false_acceptances
    ):
        raise typer.Exit(1)


@app.command("convert")
def convert(
    source: Path,
    output: Path,
    format: str,
    group_id: str = "",
    case_id: str = "",
    scenario: Path | None = None,
):
    raw = json.loads(source.read_text(encoding="utf-8"))
    if format == "transcription":
        case = transcription(raw)
    elif format == "analysis" and case_id and group_id:
        case = data_analysis(raw, case_id, group_id)
    elif format == "scheduler" and scenario:
        case = scheduler(json.loads(scenario.read_text(encoding="utf-8")), raw)
    else:
        raise typer.BadParameter("format/arguments invalid; consult docs/adapters.md")
    with output.open("x", encoding="utf-8") as stream:
        stream.write(case.model_dump_json() + "\n")


if __name__ == "__main__":
    app()
