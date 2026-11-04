"""Explicit required dimensions: missing data never silently passes a release gate."""


def strict_gate(verdicts: dict, required: list[str]) -> dict:
    if not required or len(required) != len(set(required)):
        raise ValueError("nonempty unique required dimensions needed")
    failed = [key for key in required if verdicts.get(key) != "pass"]
    return {
        "passed": not failed,
        "failed_dimensions": failed,
        "missing_dimensions": [k for k in required if k not in verdicts],
    }


def correction_effect(before_pass: bool, after_pass: bool) -> dict:
    return {
        "correction_exercised": not before_pass,
        "correction_satisfied": after_pass,
        "informative_success": not before_pass and after_pass,
    }
