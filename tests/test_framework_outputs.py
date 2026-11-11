from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from agent_eval import Criterion, EvalCase
from agent_eval.framework_outputs import (
    json_value,
    langgraph_output,
    openai_agents_output,
    smolagents_output,
)
from agent_eval.state_check import StructuredStateEvaluator


def test_typed_agent_output():
    class Output(BaseModel):
        sku: str
        available: int

    result = SimpleNamespace(final_output=Output(sku="A", available=0))
    assert openai_agents_output(result) == {"sku": "A", "available": 0}


@pytest.mark.parametrize(
    "message",
    [
        SimpleNamespace(content='{"status":"open"}'),
        {"content": [{"type": "text", "text": '{"status":"open"}'}]},
    ],
)
def test_graph_outputs(message):
    assert langgraph_output({"messages": [message]}, parse_json=True) == {"status": "open"}


def test_smol_and_non_json():
    assert smolagents_output({"total_cents": 0}) == {"total_cents": 0}
    assert smolagents_output('{"total_cents": 0}', parse_json=True) == {"total_cents": 0}
    with pytest.raises(ValueError):
        langgraph_output({"messages": []})
    with pytest.raises(ValueError):
        langgraph_output({"messages": [{"content": [{"type": "image", "url": "private"}]}]})
    with pytest.raises((ValueError, TypeError)):
        json_value({"value": float("nan")})
    with pytest.raises(TypeError):
        json_value(object())


@pytest.mark.parametrize(
    "message",
    [
        {"role": "tool", "content": "3"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "pending"}]},
    ],
)
def test_graph_incomplete_turn_not_final_answer(message):
    with pytest.raises(ValueError, match="final assistant"):
        langgraph_output({"messages": [message]})


@pytest.mark.parametrize(
    "state,answer,verdict",
    [
        (None, {"value": 0}, "insufficient_context"),
        ({}, {"value": 0}, "insufficient_context"),
        ({"verified_result": {"value": 0}}, {"value": 0}, "pass"),
        ({"verified_result": {"value": 0}}, {"value": 1}, "fail"),
        ({"verified_result": {"value": 0}}, {"different": 0}, "fail"),
    ],
)
def test_state_check(state, answer, verdict):
    case = EvalCase(
        id="case", group_id="group", input={}, output={"answer": answer}, final_state=state
    )
    criterion = Criterion(
        id="result_consistency",
        question="Matches?",
        pass_condition="match",
        fail_condition="mismatch",
    )
    assert StructuredStateEvaluator().evaluate(case, criterion).verdict == verdict
