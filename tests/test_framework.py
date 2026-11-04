import json
import sys
from contextlib import contextmanager
from copy import deepcopy

import pytest
from typer.testing import CliRunner

from agent_eval.adapters import data_analysis, scheduler, transcription
from agent_eval.audit import Contract, audit
from agent_eval.cli import app
from agent_eval.demo import AlwaysPass, demo
from agent_eval.evaluators import NumericResultEvaluator, SubprocessEvaluator, numeric_equal
from agent_eval.gates import correction_effect, strict_gate
from agent_eval.meta import Judgment, Submission, compare, digest, load_bundle, validate_submission
from agent_eval.runner import run
from agent_eval.schemas import EvalCase
from agent_eval.stability import analyze_repeats
from agent_eval.tracing import LangfuseTracer


@pytest.fixture
def bundle(tmp_path):
    demo(tmp_path / "demo")
    return load_bundle(tmp_path / "demo/cases.jsonl", tmp_path / "demo/rubric.json")


def test_demo(tmp_path):
    reports = demo(tmp_path / "demo")
    assert reports["numeric"]["match_rate"] == 1
    assert reports["always-pass"]["match_rate"] == 0.5
    assert reports["always-pass"]["false_acceptances"] == 3
    assert "authored_synthetic" in reports["numeric"]["reference_type"]
    with pytest.raises(FileExistsError):
        demo(tmp_path / "demo")


def test_no_human_labels_no_accuracy(bundle):
    result = compare(bundle, [run(bundle, AlwaysPass(), "judge")])
    assert result["reference_count"] == 0
    assert len(result["unresolved"]) == 6
    assert result["evaluators"]["judge"]["all"]["failure_detection_rate"] is None


def test_human_consensus_and_missing(bundle):
    one = run(bundle, NumericResultEvaluator(), "one")
    two = one.model_copy(deep=True)
    one.kind, two.kind, two.evaluator_id = "human", "human", "two"
    judge = run(bundle, AlwaysPass(), "judge")
    result = compare(bundle, [one, two, judge])
    assert result["reference_count"] == 6
    assert result["evaluators"]["judge"]["all"]["fn"] == 3
    two.judgments[0].verdict = "fail"
    result = compare(bundle, [one, two, judge])
    assert result["reference_count"] == 5
    assert result["unresolved"][0]["case_id"] == one.judgments[0].case_id


def test_provenance_duplicate_and_unknown(bundle):
    result = run(bundle, AlwaysPass(), "judge")
    result.dataset_hash = "wrong"
    with pytest.raises(ValueError):
        validate_submission(result, bundle)
    result.dataset_hash = bundle["dataset_hash"]
    result.judgments[0].case_id = "unknown"
    with pytest.raises(ValueError):
        validate_submission(result, bundle)
    result.judgments.append(result.judgments[0])
    with pytest.raises(ValueError):
        Submission.model_validate(result.model_dump())


def test_stable_wrong_is_not_correct(bundle):
    runs = [run(bundle, AlwaysPass(), str(i), configuration={"version": "1"}) for i in range(2)]
    result = analyze_repeats(bundle, runs, "test")
    assert result["stable_cell_rate"] == 1
    assert result["binary_pair_agreement"] == 1


def test_split_leakage_and_input_order(bundle, tmp_path):
    cases = deepcopy(bundle["cases"])
    cases[1]["split"] = "development"
    cases[1]["group_id"] = "different-name"
    path = tmp_path / "cases.jsonl"
    path.write_text("\n".join(json.dumps(c) for c in cases), encoding="utf-8")
    rubric = tmp_path / "rubric.json"
    rubric.write_text(json.dumps(bundle["rubric"]), encoding="utf-8")
    with pytest.raises(ValueError, match="cross splits"):
        load_bundle(path, rubric)
    assert digest({"a": 1, "b": 2}) == digest({"b": 2, "a": 1})


def test_adapter_preserves_zero_and_no_labels():
    case = data_analysis(
        {
            "question": "count",
            "execution_result": 0,
            "final_answer": "0",
            "numerical_evidence": 0,
            "expected": "fail",
        },
        "case",
        "group",
    )
    assert case.final_state["execution_result"] == 0
    assert "expected" not in case.model_dump_json()
    source = {
        "id": "s",
        "input": {"meetings": []},
        "correction": {"text": "cancel it", "removes_meeting_id": "secret-oracle"},
    }
    result = {
        "case_id": "s",
        "raw_schedules": [{"assignments": []}],
        "report": {"expected": "secret"},
    }
    case = scheduler(source, result)
    assert case.final_state is None
    assert "secret" not in case.model_dump_json()
    result["case_id"] = "wrong"
    with pytest.raises(ValueError):
        scheduler(source, result)
    assert (
        transcription(
            {
                "id": "m",
                "meeting_id": "g",
                "split": "test",
                "input": {"transcript": "text"},
                "output": {},
            }
        ).group_id
        == "g"
    )


@pytest.mark.parametrize(
    "a,b,equal",
    [
        (1, True, False),
        (0, 0, True),
        (1.0001, 1, True),
        ({"x": 1}, {"y": 1}, False),
        ([1, 2], [2, 1], False),
    ],
)
def test_numeric(a, b, equal):
    assert numeric_equal(a, b) is equal


def test_abstain(bundle):
    case = EvalCase.model_validate(bundle["cases"][0])
    case.final_state = None
    from agent_eval.meta import Criterion

    criterion = Criterion.model_validate(bundle["rubric"]["criteria"][0])
    assert NumericResultEvaluator().evaluate(case, criterion).verdict == "insufficient_context"


def test_errors_are_retained_and_redacted(bundle):
    class Broken:
        def evaluate(self, case, criterion):
            raise RuntimeError("SECRET-KEY")

    result = run(bundle, Broken(), "broken")
    assert len(result.metadata["errors"]) == 6
    assert not result.judgments
    assert "SECRET-KEY" not in result.model_dump_json()


def test_wrong_identity(bundle):
    class Wrong:
        def evaluate(self, case, criterion):
            return Judgment(
                case_id="wrong", criterion_id=criterion.id, verdict="pass", rationale="wrong"
            )

    result = run(bundle, Wrong(), "wrong")
    assert len(result.metadata["errors"]) == 6


def test_subprocess_protocol(bundle):
    command = [
        sys.executable,
        "-c",
        "import sys,json; r=json.load(sys.stdin); "
        "print(json.dumps(dict(case_id=r['case']['id'],criterion_id=r['criterion']['id'],"
        "verdict='pass',rationale='offline test')))",
    ]
    result = run(bundle, SubprocessEvaluator(command), "subprocess")
    assert len(result.judgments) == 6
    assert not result.metadata["errors"]


def test_trace_privacy_and_flush(bundle):
    class Span:
        trace_id, id = "trace", "span"

        def update(self, **kwargs):
            outputs.append(kwargs)

    class Client:
        flushed = False

        @contextmanager
        def start_as_current_observation(self, **kwargs):
            requests.append(kwargs)
            yield Span()

        def create_score(self, **kwargs):
            scores.append(kwargs)

        def flush(self):
            self.flushed = True

    requests, outputs, scores = [], [], []
    client = Client()
    result = run(bundle, NumericResultEvaluator(), "numeric", tracer=LangfuseTracer(client))
    assert client.flushed and len(scores) == 6 and len(result.metadata["traces"]) == 6
    assert all(r["input"] is None for r in requests)
    assert all(set(o["output"]) == {"verdict"} for o in outputs)


def test_gate_and_correction():
    assert not strict_gate({}, ["hard"])["passed"]
    assert not strict_gate({"hard": "insufficient_context"}, ["hard"])["passed"]
    assert strict_gate({"hard": "pass"}, ["hard"])["passed"]
    with pytest.raises(ValueError):
        strict_gate({}, [])
    assert not correction_effect(True, True)["informative_success"]
    assert correction_effect(False, True)["informative_success"]


def test_audit_gate_cli(bundle, tmp_path):
    base = tmp_path / "demo"
    result = CliRunner().invoke(
        app,
        [
            "audit",
            str(base / "cases.jsonl"),
            str(base / "rubric.json"),
            str(base / "always-pass.json"),
            str(base / "contracts.json"),
            str(tmp_path / "gate.json"),
        ],
    )
    assert result.exit_code == 1
    assert json.loads((tmp_path / "gate.json").read_text())["false_acceptances"] == 3


def test_html_no_judgments_or_script_injection(bundle, tmp_path):
    from agent_eval.review import export_review

    bundle["cases"][0]["output"] = "</script><script>alert(1)</script>"
    export_review(bundle, tmp_path / "review.html")
    html = (tmp_path / "review.html").read_text(encoding="utf-8")
    assert "</script><script>alert(1)" not in html
    assert "always-pass" not in html


def test_contract_validation(bundle):
    result = run(bundle, AlwaysPass(), "control")
    contract = Contract(
        case_id="analysis-a", criterion_id="numerical_evidence", expected="pass", defect="control"
    )
    with pytest.raises(ValueError):
        audit(bundle, result, [contract, contract])
