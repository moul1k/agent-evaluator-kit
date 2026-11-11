"""Optional actual-SDK type/loop tests. No network or paid model calls."""

import importlib.util
import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from agent_eval.framework_outputs import langgraph_output, openai_agents_output, smolagents_output


def test_real_openai_run_result():
    agents = pytest.importorskip("agents")
    from agents.result import RunResult

    class Output(BaseModel):
        available: int

    result = RunResult(
        input="synthetic",
        new_items=[],
        raw_responses=[],
        final_output=Output(available=0),
        input_guardrail_results=[],
        output_guardrail_results=[],
        tool_input_guardrail_results=[],
        tool_output_guardrail_results=[],
        context_wrapper=agents.RunContextWrapper(context=None),
        _last_agent=agents.Agent(name="test"),
    )
    assert openai_agents_output(result) == {"available": 0}


def test_real_langchain_message():
    messages = pytest.importorskip("langchain_core.messages")
    state = {"messages": [messages.AIMessage(content='{"status":"closed"}')]}
    assert langgraph_output(state, parse_json=True) == {"status": "closed"}


def test_real_smol_tool_loop_without_network(monkeypatch):
    pytest.importorskip("smolagents")
    httpx = pytest.importorskip("httpx")
    monkeypatch.setenv("OPENAI_API_KEY", "test-placeholder")
    path = Path(__file__).resolve().parents[1] / "scripts/run_agent_interop.py"
    spec = importlib.util.spec_from_file_location("interop_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    requests, calls = [], []
    expected = {"invoice_id": "I1", "total_cents": 875}

    def respond(request):
        body = json.loads(request.content)
        requests.append(body)
        assert body["reasoning_effort"] == "none"
        assert "stop" not in body
        assert body["max_completion_tokens"] == 512
        name, arguments = (
            ("invoice_lookup", {"invoice_id": "I1"})
            if len(requests) == 1
            else ("final_answer", {"answer": expected})
        )
        return httpx.Response(
            200,
            json={
                "id": "mock",
                "object": "chat.completion",
                "created": 0,
                "model": "gpt-6-luna",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": str(len(requests)),
                                    "type": "function",
                                    "function": {"name": name, "arguments": json.dumps(arguments)},
                                }
                            ],
                        },
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result, _ = module.smol_agent(client, {"message": "Read I1"}, calls, omit_stop=True)
    assert smolagents_output(result, parse_json=True) == expected
    assert len(calls) == 1 and len(requests) == 2
