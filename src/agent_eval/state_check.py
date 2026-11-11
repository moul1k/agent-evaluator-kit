"""A narrow evidence-consistency plugin, not a universal task-success oracle."""

from .evaluators import numeric_equal
from .meta import Judgment


class StructuredStateEvaluator:
    def evaluate(self, case, criterion):
        if criterion.id != "result_consistency":
            raise ValueError("unsupported criterion")
        state = case.final_state
        if state is None or "verified_result" not in state:
            verdict = "insufficient_context"
        elif not isinstance(case.output, dict) or "answer" not in case.output:
            verdict = "fail"
        else:
            verdict = (
                "pass" if numeric_equal(case.output["answer"], state["verified_result"]) else "fail"
            )
        return Judgment(
            case_id=case.id,
            criterion_id=criterion.id,
            verdict=verdict,
            rationale="Compare structured answer with independently captured tool truth; "
            "missing state must abstain.",
        )
