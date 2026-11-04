"""Public, domain-neutral contracts and evaluator interfaces."""

from .integration import CallableEvaluator, FieldMapping, RoutedEvaluator, acapture, capture
from .meta import Criterion, Judgment, Rubric, Submission, bundle_from_cases, compare, load_bundle
from .schemas import EvalCase

__all__ = [
    "Criterion",
    "Judgment",
    "Rubric",
    "Submission",
    "EvalCase",
    "compare",
    "load_bundle",
    "bundle_from_cases",
    "CallableEvaluator",
    "FieldMapping",
    "RoutedEvaluator",
    "capture",
    "acapture",
]
