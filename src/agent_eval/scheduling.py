"""Original deterministic scheduling plugin, independent of upstream source code.

Only the explicit structured weekly constraints are checked, not soft quality.
Natural-language corrections require resolution before deterministic grading.
"""

import re

from .meta import Judgment

DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri")


def minutes(value):
    if not isinstance(value, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
        raise ValueError("time must be valid HH:MM")
    hour, minute = map(int, value.split(":"))
    return hour * 60 + minute


def violations(scenario, schedule):
    meetings = scenario["meetings"]
    by_id = {m["id"]: m for m in meetings}
    if len(by_id) != len(meetings):
        raise ValueError("duplicate requested meeting IDs")
    rows = schedule["assignments"]
    errors, seen, intervals = [], set(), []
    for row in rows:
        mid, day = row["meeting_id"], row["day"]
        if mid in seen:
            errors.append(f"duplicate assignment: {mid}")
        seen.add(mid)
        if mid not in by_id:
            errors.append(f"unknown meeting: {mid}")
            continue
        if day not in DAYS:
            raise ValueError("invalid day")
        meeting = by_id[mid]
        duration = meeting["duration_minutes"]
        if isinstance(duration, bool) or not isinstance(duration, int) or duration <= 0:
            raise ValueError("duration must be a positive integer")
        start = minutes(row["start_time"])
        end = start + duration
        if start < 540 or end > 1020:
            errors.append(f"outside work hours: {mid}")
        if meeting.get("fixed_day") and day != meeting["fixed_day"]:
            errors.append(f"wrong fixed day: {mid}")
        if meeting.get("not_before") and start < minutes(meeting["not_before"]):
            errors.append(f"before earliest start: {mid}")
        if meeting.get("not_after_day") and DAYS.index(day) > DAYS.index(meeting["not_after_day"]):
            errors.append(f"after deadline day: {mid}")
        for block in scenario.get("blocked_times", []):
            if (
                day == block["day"]
                and start < minutes(block["end"])
                and minutes(block["start"]) < end
            ):
                errors.append(f"blocked interval: {mid}")
        attendees = set(meeting.get("attendees", []))
        for other, other_day, other_start, other_end, people in intervals:
            if day == other_day and start < other_end and other_start < end and attendees & people:
                errors.append(f"shared-attendee overlap: {other}/{mid}")
        intervals.append((mid, day, start, end, attendees))
    errors.extend(f"missing meeting: {mid}" for mid in by_id.keys() - seen)
    return sorted(errors)


class ScheduleConstraintEvaluator:
    def evaluate(self, case, criterion):
        if criterion.id != "schedule_hard_constraints":
            raise ValueError("unsupported criterion")
        if case.input.get("correction_text"):
            verdict, evidence = "insufficient_context", []
            rationale = "Resolve the correction into structured constraints before hard grading."
        else:
            evidence = violations(case.input["scenario"], case.output)
            verdict = "fail" if evidence else "pass"
            rationale = "Check explicit weekly constraints; no soft-quality or execution claim."
        return Judgment(
            case_id=case.id,
            criterion_id=criterion.id,
            verdict=verdict,
            rationale=rationale,
            evidence=evidence,
        )
