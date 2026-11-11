import json
from types import SimpleNamespace

import pytest

from agent_eval.request_budget import RequestBudget


def request(**overrides):
    body = {"model": "gpt-6-luna", "max_output_tokens": 512, **overrides}
    return SimpleNamespace(
        url=SimpleNamespace(host="api.openai.com", path="/v1/responses"),
        content=json.dumps(body).encode(),
    )


def test_shared_cap_and_usage():
    budget = RequestBudget(limit=1)
    r = request()
    budget.before(r)
    budget.after(
        SimpleNamespace(
            request=r,
            status_code=200,
            json=lambda: {"usage": {"input_tokens": 10, "output_tokens": 5}},
        )
    )
    assert budget.rows[0]["input_tokens"] == 10
    with pytest.raises(RuntimeError):
        budget.before(request())
    assert len(budget.rows) == 1


@pytest.mark.parametrize(
    "change",
    [
        {"model": "other"},
        {"max_output_tokens": 513},
        {"max_output_tokens": None},
        {"max_output_tokens": True},
        {"stream": True},
    ],
)
def test_fail_before_request(change):
    budget = RequestBudget()
    with pytest.raises(ValueError):
        budget.before(request(**change))
    assert not budget.rows


@pytest.mark.parametrize("status", [401, 403, 429])
def test_halt(status):
    budget = RequestBudget()
    r = request()
    budget.before(r)
    budget.after(SimpleNamespace(request=r, status_code=status, json=lambda: {}))
    with pytest.raises(RuntimeError):
        budget.before(request())


def test_wrong_host_and_body_limit():
    budget = RequestBudget()
    r = request()
    r.url.host = "other.example"
    with pytest.raises(ValueError):
        budget.before(r)
    with pytest.raises(ValueError):
        RequestBudget(max_body_bytes=1).before(request())
