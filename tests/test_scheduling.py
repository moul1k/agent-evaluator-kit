from copy import deepcopy

import pytest

from agent_eval.scheduling import minutes, violations


@pytest.fixture
def scenario():
    return {
        "meetings": [
            {"id": "a", "duration_minutes": 30, "attendees": ["X"]},
            {"id": "b", "duration_minutes": 45, "attendees": ["X"]},
        ],
        "blocked_times": [],
    }


@pytest.fixture
def schedule():
    return {
        "assignments": [
            {"meeting_id": "a", "day": "Mon", "start_time": "09:00"},
            {"meeting_id": "b", "day": "Mon", "start_time": "09:30"},
        ]
    }


def test_valid_and_adjacent(scenario, schedule):
    assert not violations(scenario, schedule)


@pytest.mark.parametrize(
    "change,expected",
    [
        ({"start_time": "09:15"}, "overlap"),
        ({"start_time": "16:30"}, "outside"),
        ({"meeting_id": "unknown"}, "unknown"),
        ({"meeting_id": "a"}, "duplicate"),
    ],
)
def test_invalid(scenario, schedule, change, expected):
    schedule["assignments"][1].update(change)
    assert any(expected in e for e in violations(scenario, schedule))


def test_blocked_fixed_deadline_missing(scenario, schedule):
    scenario["blocked_times"] = [{"day": "Mon", "start": "09:00", "end": "09:15"}]
    scenario["meetings"][0].update(fixed_day="Tue", not_before="10:00")
    scenario["meetings"][1]["not_after_day"] = "Mon"
    schedule["assignments"][1]["day"] = "Tue"
    errors = violations(scenario, schedule)
    assert len(errors) == 4
    schedule["assignments"].pop()
    assert any("missing" in e for e in violations(scenario, schedule))


@pytest.mark.parametrize("time", ["24:00", "9:00", "10:60", "bad", None])
def test_malformed(time):
    with pytest.raises(ValueError):
        minutes(time)


def test_no_shared_attendee_overlap_allowed(scenario, schedule):
    scenario = deepcopy(scenario)
    scenario["meetings"][1]["attendees"] = ["Y"]
    schedule["assignments"][1]["start_time"] = "09:00"
    assert not violations(scenario, schedule)
