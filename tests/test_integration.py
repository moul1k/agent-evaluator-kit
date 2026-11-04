import asyncio
import json
from contextlib import contextmanager
from types import SimpleNamespace
from zipfile import ZipFile

import pytest
from typer.testing import CliRunner

from agent_eval import (
    CallableEvaluator,
    Criterion,
    EvalCase,
    FieldMapping,
    RoutedEvaluator,
    Rubric,
    acapture,
    bundle_from_cases,
    capture,
)
from agent_eval.cli import app
from agent_eval.config import load_credentials, tracing_enabled
from agent_eval.demo import AlwaysPass
from agent_eval.integration import pointer
from agent_eval.runner import run
from agent_eval.tracing import LangfuseTracer


@pytest.fixture
def bundle():
    criterion = Criterion(
        id="grounded", question="Grounded?", pass_condition="yes", fail_condition="no"
    )
    cases = [
        EvalCase(id=str(i), group_id=str(i), input={"request": str(i)}, output="answer")
        for i in range(3)
    ]
    return bundle_from_cases(cases, Rubric(id="rubric", version="1", criteria=[criterion]))


def test_capture_snapshot_and_object_output():
    original = {"request": "hello"}

    def agent(value):
        value["mutated"] = True
        return SimpleNamespace(content="answer")

    case = capture(agent, original, case_id="a", group_id="g", output_adapter=lambda r: r.content)
    assert case.output == "answer" and case.input == original == {"request": "hello"}
    assert case.final_state is None


def test_async_capture():
    async def agent(value):
        return {"answer": value["question"]}

    case = asyncio.run(acapture(agent, {"question": "hi"}, case_id="a", group_id="g"))
    assert case.output == {"answer": "hi"}
    with pytest.raises(TypeError, match="acapture"):
        capture(agent, {}, case_id="a", group_id="g")


def test_mapping_only_selected_fields():
    raw = {
        "run": {"key": "a", "source": "g"},
        "request": "hello",
        "result": [{"content": "answer"}],
        "oracle": "HIDDEN",
    }
    case = FieldMapping(
        id="/run/key", group_id="/run/source", input="/request", output="/result/0/content"
    ).convert(raw)
    assert case.input == {"value": "hello"} and case.output == "answer"
    assert "HIDDEN" not in case.model_dump_json()
    assert pointer({"a/b": {"~": 3}}, "/a~1b/~0") == 3


@pytest.mark.parametrize("path", ["bad", "/~2", "/result/01", "/result/-1"])
def test_bad_pointer(path):
    with pytest.raises((ValueError, KeyError)):
        pointer({"result": [1]}, path)


def test_mapping_missing_field_and_invalid_json():
    with pytest.raises(KeyError):
        FieldMapping().convert({})
    with pytest.raises(ValueError):
        EvalCase(id="a", group_id="g", input={}, output=float("nan"))


def test_callable_and_routing(bundle):
    seen = []

    def score(case, criterion):
        seen.append((case, criterion))
        return {"verdict": "pass", "rationale": "Existing scorer says supported"}

    routed = RoutedEvaluator({"grounded": CallableEvaluator(score)})
    submission = run(bundle, routed, "existing")
    assert len(submission.judgments) == 3 and len(seen) == 3
    fallback = run(bundle, RoutedEvaluator({}), "missing")
    assert all(j.verdict == "insufficient_context" for j in fallback.judgments)


def test_max_calls_prevents_all_spend(bundle):
    class Never:
        def evaluate(self, case, criterion):
            raise AssertionError("must not be called")

    with pytest.raises(ValueError, match="max_calls"):
        run(bundle, Never(), "never", max_calls=2)


@pytest.mark.parametrize("status", [401, 403, 429])
def test_stop_on_provider_errors(bundle, status):
    class Error(Exception):
        status_code = status

    class Broken:
        def evaluate(self, case, criterion):
            raise Error("DO-NOT-LOG-SECRET")

    submission = run(bundle, Broken(), "broken")
    assert len(submission.metadata["errors"]) == 1
    assert len(submission.metadata["skipped"]) == 2
    assert "DO-NOT-LOG-SECRET" not in submission.model_dump_json()


@pytest.mark.parametrize("phase", ["enter", "exit", "score", "flush"])
def test_trace_errors_preserve_judgments(bundle, phase):
    class BrokenTracer:
        @contextmanager
        def observation(self, *args):
            if phase == "enter":
                raise RuntimeError("secret")
            yield SimpleNamespace(trace_id="trace")
            if phase == "exit":
                raise RuntimeError("secret")

        def record(self, *args, **kwargs):
            if phase == "score":
                raise RuntimeError("secret")

        def flush(self):
            if phase == "flush":
                raise RuntimeError("secret")

    submission = run(bundle, AlwaysPass(), "judge", tracer=BrokenTracer())
    assert len(submission.judgments) == 3
    assert submission.metadata["tracing_errors"]
    assert "secret" not in submission.model_dump_json()


def test_trace_rate_limit_no_retry():
    calls = []

    class Error(Exception):
        status_code = 429

    def get(*args, **kwargs):
        calls.append(kwargs)
        raise Error("private message")

    client = SimpleNamespace(api=SimpleNamespace(observations=SimpleNamespace(get_many=get)))
    assert LangfuseTracer(client).verify_trace("id")["status"] == "rate_limited"
    assert calls[0]["request_options"]["max_retries"] == 0
    assert len(calls) == 1


def test_docx_credentials_runtime_only(tmp_path, monkeypatch):
    for name in (
        "OPENAI_API_KEY",
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY",
        "LANGFUSE_BASE_URL",
    ):
        monkeypatch.delenv(name, raising=False)
    key = "sk-proj-" + "a" * 24
    doc = tmp_path / "key.docx"
    with ZipFile(doc, "w") as archive:
        archive.writestr(
            "word/document.xml",
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:p><w:r><w:t>'
            + key
            + "</w:t></w:r></w:p></w:document>",
        )
    load_credentials(doc)
    import os

    assert os.environ["OPENAI_API_KEY"] == key
    assert not tracing_enabled(None)
    assert tracing_enabled(True) and not tracing_enabled(False)


def test_ambiguous_credentials_atomic(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    path = tmp_path / "keys.txt"
    path.write_text("sk-proj-" + "a" * 24 + "\nsk-proj-" + "b" * 24)
    with pytest.raises(ValueError):
        load_credentials(path)
    import os

    assert "OPENAI_API_KEY" not in os.environ


def test_import_cli(tmp_path):
    path = tmp_path / "input.jsonl"
    path.write_text(json.dumps({"id": "a", "group_id": "g", "input": "question", "output": 0}))
    mapping = tmp_path / "mapping.json"
    mapping.write_text("{}")
    output = tmp_path / "cases.jsonl"
    result = CliRunner().invoke(app, ["import-records", str(path), str(mapping), str(output)])
    assert result.exit_code == 0
    assert json.loads(output.read_text())["output"] == 0
