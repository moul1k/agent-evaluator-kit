"""Upstream integration tests are opt-in; fixtures here are original synthetic inputs."""

import os
from copy import deepcopy
from pathlib import Path

import pytest

from agent_eval import Criterion, Rubric, bundle_from_cases
from agent_eval.adapters import data_analysis, scheduler
from agent_eval.demo import AlwaysPass
from agent_eval.native import DomainRouter, NativeEvaluator
from agent_eval.runner import run

AAYUSH = "1aa83e6eedab4c7438f7c4184bf482096f99d8dc"
SRIHARI = "cb1084253388eb5d452618c36cf1dadaf0359ed4"


def rubric(names):
    return Rubric(
        id="native",
        version="1",
        criteria=[
            Criterion(
                id=name,
                question=f"Does {name} pass the documented threshold?",
                pass_condition="Native score meets the explicit threshold.",
                fail_condition="Native score is below the threshold.",
            )
            for name in names
        ],
    )


@pytest.mark.parametrize("thresholds", [{}, {"x": True}, {"x": float("nan")}, {"x": 2}])
def test_threshold_validation(thresholds):
    with pytest.raises(ValueError):
        NativeEvaluator("analysis", Path("."), thresholds, expected_commit=AAYUSH)


def test_domain_router_errors():
    router = DomainRouter(lambda case: "unknown", {})
    with pytest.raises(ValueError):
        router.evaluate(None, None)


def test_native_commit_guard():
    with pytest.raises(ValueError, match="commit"):
        NativeEvaluator("analysis", Path("."), {"x": 1}, expected_commit="wrong")


@pytest.mark.skipif(not os.getenv("AAYUSH_REPO"), reason="set AAYUSH_REPO to pinned local checkout")
def test_aayush_full_native_engine():
    source = {
        "question": "How many completed jobs?",
        "dataset_schema": {"columns": ["status"]},
        "analysis_plan": {"analysis_type": "count_by_group"},
        "generated_code": "result = 3",
        "execution_result": {"done": 3},
        "final_answer": "done: 3",
        "numerical_evidence": {"done": 3},
        "errors": None,
    }
    good = data_analysis(source, "good", "source")
    source["numerical_evidence"] = {"done": 99}
    bad = data_analysis(source, "bad", "source")
    dimensions = [
        "numerical_correctness",
        "data_grounding",
        "method_correctness",
        "completeness",
        "hallucination_free",
    ]
    plugin = NativeEvaluator(
        "analysis",
        Path(os.environ["AAYUSH_REPO"]),
        {d: 0.9 for d in dimensions},
        expected_commit=AAYUSH,
    )
    bundle = bundle_from_cases([good, bad], rubric(dimensions))
    result = run(bundle, plugin, "aayush-native")
    assert not result.metadata["errors"]
    assert len(result.judgments) == 10
    values = {(j.case_id, j.criterion_id): j.verdict for j in result.judgments}
    assert values["good", "numerical_correctness"] == "pass"
    assert values["bad", "numerical_correctness"] == "fail"
    assert plugin.configuration["commit"] == AAYUSH


@pytest.mark.skipif(
    not os.getenv("SRIHARI_REPO"), reason="set SRIHARI_REPO to pinned local checkout"
)
def test_srihari_correction_and_regression():
    scenario = {
        "id": "cancel",
        "description": "Synthetic cancellation",
        "input": {
            "meetings": [
                {"id": "a", "title": "A", "duration_minutes": 30},
                {"id": "b", "title": "B", "duration_minutes": 30},
            ]
        },
        "correction": {"text": "Cancel A", "removes_meeting_id": "a"},
    }
    first = {
        "assignments": [
            {"meeting_id": "a", "day": "Mon", "start_time": "09:00"},
            {"meeting_id": "b", "day": "Mon", "start_time": "10:00"},
        ]
    }
    final = deepcopy(first)
    final["assignments"].pop(0)
    case = scheduler(scenario, {"case_id": "cancel", "raw_schedules": [first, final]})
    dims = ["hard_pass", "regression_score", "removed_meeting_absent", "correction_exercised"]
    plugin = NativeEvaluator(
        "scheduler",
        Path(os.environ["SRIHARI_REPO"]),
        {d: 1 for d in dims},
        expected_commit=SRIHARI,
        contexts={case.id: scenario},
    )
    result = run(bundle_from_cases([case], rubric(dims)), plugin, "srihari-native")
    assert not result.metadata["errors"]
    assert all(j.verdict == "pass" for j in result.judgments)
    case.output = first
    result = run(bundle_from_cases([case], rubric(dims)), plugin, "ignored-correction")
    values = {j.criterion_id: j.verdict for j in result.judgments}
    assert values["removed_meeting_absent"] == "fail"
    assert values["hard_pass"] == "fail"


def test_domain_router_common_runner():
    source = {
        "question": "Count",
        "execution_result": 0,
        "numerical_evidence": 0,
        "final_answer": "0",
    }
    cases = [data_analysis(source, "analysis", "source")]
    router = DomainRouter(
        lambda c: "analysis" if "question" in c.input else "other", {"analysis": AlwaysPass()}
    )
    result = run(
        bundle_from_cases(cases, rubric(["shared"])),
        router,
        "router",
        configuration={"classifier_version": "1", "routes": {"analysis": "control"}},
    )
    assert len(result.judgments) == 1
