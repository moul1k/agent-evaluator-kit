"""Six original cross-domain smoke cases, including an always-pass negative control."""

import json
from pathlib import Path

from .audit import Contract, audit
from .evaluators import NumericResultEvaluator
from .meta import Criterion, Judgment, Rubric, load_bundle
from .review import export_review
from .runner import run
from .schemas import EvalCase


class AlwaysPass:
    def evaluate(self, case, criterion):
        return Judgment(
            case_id=case.id,
            criterion_id=criterion.id,
            verdict="pass",
            rationale="Deliberately broken negative control.",
        )


def write_json(path, data):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(data, stream, indent=2, ensure_ascii=False)


def demo(directory: Path, tracer=None):
    directory.mkdir(parents=True, exist_ok=False)
    rubric = Rubric(
        id="structured-evidence",
        version="1.0.0",
        criteria=[
            Criterion(
                id="numerical_evidence",
                question="Does structured evidence match the execution result?",
                pass_condition="Values and field identities match within 0.0005 absolute tolerance.",
                fail_condition="Evidence differs from execution result; missing evidence must abstain.",
            )
        ],
    )
    cases, contracts = [], []
    for domain, value in [("analysis", 0.875), ("scheduler", 45), ("meeting", 3)]:
        for correct in (True, False):
            cid = f"{domain}-{'a' if correct else 'b'}"
            cases.append(
                EvalCase(
                    id=cid,
                    group_id=domain,
                    input={"domain": domain, "request": "Report the verified numerical result."},
                    output={"numerical_evidence": value if correct else value + 1},
                    final_state={"execution_result": value},
                )
            )
            contracts.append(
                Contract(
                    case_id=cid,
                    criterion_id="numerical_evidence",
                    expected="pass" if correct else "fail",
                    defect="control" if correct else "wrong_number",
                )
            )
    write_json(directory / "rubric.json", rubric.model_dump())
    with (directory / "cases.jsonl").open("x", encoding="utf-8") as stream:
        for case in cases:
            stream.write(case.model_dump_json() + "\n")
    write_json(directory / "contracts.json", [c.model_dump() for c in contracts])
    bundle = load_bundle(directory / "cases.jsonl", directory / "rubric.json")
    export_review(bundle, directory / "review.html")
    reports = {}
    for name, evaluator in [("numeric", NumericResultEvaluator()), ("always-pass", AlwaysPass())]:
        result = run(
            bundle, evaluator, name, tracer=tracer, configuration={"plugin": name, "version": "1"}
        )
        write_json(directory / f"{name}.json", result.model_dump(mode="json"))
        reports[name] = audit(bundle, result, contracts)
    write_json(directory / "report.json", reports)
    return reports
