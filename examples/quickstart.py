"""Run from an installed checkout: python examples/quickstart.py. No API calls."""

from pathlib import Path

from agent_eval import (
    CallableEvaluator,
    Criterion,
    Rubric,
    bundle_from_cases,
    capture,
)
from agent_eval.demo import write_json
from agent_eval.runner import run


def my_agent(request):
    # Replace this with your agent.run, agent.invoke, or an SDK-neutral lambda.
    return {"answer": request["message"]}


def my_check(case, criterion):
    return {
        "verdict": "pass" if case["output"]["answer"] == case["input"]["message"] else "fail",
        "rationale": "Check the deliberately narrow echo contract.",
    }


case = capture(my_agent, {"message": "hello"}, case_id="run-1", group_id="request-1")
rubric = Rubric(
    id="echo-contract",
    version="1",
    criteria=[
        Criterion(
            id="echo",
            question="Is the message preserved?",
            pass_condition="Exact message preserved.",
            fail_condition="Message changed or omitted.",
        )
    ],
)
bundle = bundle_from_cases([case], rubric)
submission = run(
    bundle,
    CallableEvaluator(my_check),
    "echo-check-v1",
    configuration={"check": "echo", "version": "1"},
)
directory = Path("artifacts/quickstart")
directory.mkdir(parents=True, exist_ok=False)
write_json(directory / "submission.json", submission.model_dump(mode="json"))
print(submission.judgments[0].verdict)
