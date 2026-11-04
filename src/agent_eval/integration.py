"""Framework-neutral integration: callables and explicit RFC 6901 field mappings."""

import inspect
import re
from copy import deepcopy
from typing import Callable

from .meta import Judgment
from .schemas import EvalCase, StrictModel


def pointer(document, path):
    if path == "":
        return document
    if not path.startswith("/"):
        raise ValueError("JSON pointer must be empty or start with /")
    if re.search(r"~(?![01])", path):
        raise ValueError("invalid JSON pointer escape")
    current = document
    for token in path[1:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            if not re.fullmatch(r"0|[1-9][0-9]*", token):
                raise ValueError("invalid array index")
            current = current[int(token)]
        else:
            current = current[token]
    return current


class FieldMapping(StrictModel):
    id: str = "/id"
    group_id: str = "/group_id"
    input: str = "/input"
    output: str = "/output"
    tool_trace: str | None = None
    final_state: str | None = None
    split: str = "test"

    def convert(self, record) -> EvalCase:
        source = pointer(record, self.input)
        return EvalCase(
            id=pointer(record, self.id),
            group_id=pointer(record, self.group_id),
            split=self.split,
            input=source if isinstance(source, dict) else {"value": source},
            output=pointer(record, self.output),
            tool_trace=pointer(record, self.tool_trace) if self.tool_trace is not None else [],
            final_state=pointer(record, self.final_state) if self.final_state is not None else None,
        )


class CallableEvaluator:
    """Wrap an existing scorer; mapping results must use the typed verdict vocabulary."""

    def __init__(self, function: Callable):
        self.function = function

    def evaluate(self, case, criterion):
        result = self.function(case.model_dump(mode="json"), criterion.model_dump())
        if isinstance(result, Judgment):
            return result
        return Judgment.model_validate({"case_id": case.id, "criterion_id": criterion.id, **result})


class RoutedEvaluator:
    """Use domain checks for selected criteria and a model judge for the rest."""

    def __init__(self, routes: dict, fallback=None):
        self.routes, self.fallback = routes, fallback

    def evaluate(self, case, criterion):
        evaluator = self.routes.get(criterion.id, self.fallback)
        self.last_usage = {}
        if evaluator is None:
            return Judgment(
                case_id=case.id,
                criterion_id=criterion.id,
                verdict="insufficient_context",
                rationale="No evaluator configured.",
            )
        try:
            return evaluator.evaluate(case, criterion)
        finally:
            self.last_usage = getattr(evaluator, "last_usage", {})


def capture(
    function,
    input: dict,
    *,
    case_id: str,
    group_id: str,
    output_adapter: Callable | None = None,
    tool_trace=None,
    final_state=None,
    split="test",
) -> EvalCase:
    """Call an agent with one dict argument; never infer execution evidence from its output."""
    source = deepcopy(input)
    result = function(deepcopy(input))
    if inspect.isawaitable(result):
        if inspect.iscoroutine(result):
            result.close()
        raise TypeError("Use acapture for async agents")
    return EvalCase(
        id=case_id,
        group_id=group_id,
        split=split,
        input=source,
        output=output_adapter(result) if output_adapter else result,
        tool_trace=tool_trace or [],
        final_state=final_state,
    )


async def acapture(
    function,
    input: dict,
    *,
    case_id: str,
    group_id: str,
    output_adapter: Callable | None = None,
    tool_trace=None,
    final_state=None,
    split="test",
) -> EvalCase:
    source = deepcopy(input)
    result = await function(deepcopy(input))
    return EvalCase(
        id=case_id,
        group_id=group_id,
        split=split,
        input=source,
        output=output_adapter(result) if output_adapter else result,
        tool_trace=tool_trace or [],
        final_state=final_state,
    )
