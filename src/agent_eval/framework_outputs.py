"""Dependency-free output adapters for three agent SDK result shapes.

These normalize outputs only; they never infer tool execution or final state.
"""

import json


def json_value(value):
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    # Fail on arbitrary SDK objects, nonfinite numbers, and unsupported nested types.
    return json.loads(json.dumps(value, allow_nan=False))


def openai_agents_output(result):
    return json_value(result.final_output)


def langgraph_output(state, *, parse_json=False):
    messages = state.get("messages", [])
    if not messages:
        raise ValueError("LangGraph result has no messages")
    last = messages[-1]
    role = (
        last.get("role", last.get("type"))
        if isinstance(last, dict)
        else getattr(last, "type", None)
    )
    tool_calls = (
        last.get("tool_calls") if isinstance(last, dict) else getattr(last, "tool_calls", None)
    )
    if role in ("tool", "human", "user", "system") or tool_calls:
        raise ValueError("LangGraph run has not produced a final assistant answer")
    content = last.get("content") if isinstance(last, dict) else last.content
    if isinstance(content, list):
        if any(
            not isinstance(b, dict) or b.get("type") not in ("text", "output_text") for b in content
        ):
            raise ValueError("explicit adapter required for non-text content blocks")
        content = "".join(b["text"] for b in content)
    return json.loads(content) if parse_json and isinstance(content, str) else json_value(content)


def smolagents_output(result, *, parse_json=False):
    return json.loads(result) if parse_json and isinstance(result, str) else json_value(result)
