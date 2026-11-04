from types import SimpleNamespace

import pytest

from agent_eval.evaluators import OpenAIEvaluator
from agent_eval.meta import Criterion, Judgment
from agent_eval.schemas import EvalCase


@pytest.mark.parametrize("missing", [False, True])
def test_structured_model_adapter(missing):
    requests = []
    case = EvalCase(id="case", group_id="group", input={"request": "check"}, output={})
    criterion = Criterion(id="truth", question="True?", pass_condition="yes", fail_condition="no")
    judgment = Judgment(
        case_id="case",
        criterion_id="truth",
        verdict="insufficient_context",
        rationale="No evidence",
    )

    def parse(**kwargs):
        requests.append(kwargs)
        return SimpleNamespace(output_parsed=None if missing else judgment)

    plugin = OpenAIEvaluator(
        "gpt-6-luna", client=SimpleNamespace(responses=SimpleNamespace(parse=parse))
    )
    if missing:
        with pytest.raises(ValueError):
            plugin.evaluate(case, criterion)
    else:
        assert plugin.evaluate(case, criterion).verdict == "insufficient_context"
    assert requests[0]["max_output_tokens"] == 1000
    assert requests[0]["model"] == "gpt-6-luna"
    assert "expected" not in requests[0]["input"][1]["content"]
