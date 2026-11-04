"""Optional bridges to separately installed upstream grading engines.

No upstream source is bundled. Only trusted local checkouts should be executed.
"""

import json
import math
import subprocess
import sys
from pathlib import Path

from .meta import Judgment, digest


class NativeEvaluator:
    def __init__(
        self,
        project: str,
        repository: Path,
        thresholds: dict[str, float],
        *,
        expected_commit: str,
        contexts=None,
        python=sys.executable,
        timeout=60,
    ):
        if project not in ("analysis", "scheduler"):
            raise ValueError("project must be analysis or scheduler")
        if not thresholds or any(
            isinstance(v, bool)
            or not isinstance(v, (float, int))
            or not math.isfinite(v)
            or not 0 <= v <= 1
            for v in thresholds.values()
        ):
            raise ValueError("explicit finite per-dimension thresholds in [0,1] required")
        if timeout <= 0:
            raise ValueError("positive timeout required")
        self.repository = Path(repository).resolve(strict=True)
        actual = subprocess.check_output(
            ["git", "-C", str(self.repository), "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        if actual != expected_commit:
            raise ValueError("upstream commit differs from explicit expected_commit")
        self.project, self.thresholds = project, thresholds
        self.contexts, self.python, self.timeout = contexts or {}, python, timeout
        self.configuration = {
            "plugin": "native",
            "project": project,
            "commit": actual,
            "thresholds": thresholds,
            "bridge_version": "1",
            "context_hash": digest(self.contexts),
        }

    def evaluate(self, case, criterion):
        if criterion.id not in self.thresholds:
            raise ValueError("criterion needs an explicit native threshold")
        request = {"case": case.model_dump(mode="json"), "context": self.contexts.get(case.id)}
        result = subprocess.run(
            [self.python, "-m", "agent_eval.native_worker", self.project, str(self.repository)],
            input=json.dumps(request),
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=True,
            timeout=self.timeout,
            shell=False,
        )
        report = json.loads(result.stdout)
        score = report["scores"].get(criterion.id)
        if score is None:
            verdict = "not_applicable"
        elif (
            isinstance(score, bool)
            or not isinstance(score, (float, int))
            or not math.isfinite(score)
        ):
            raise ValueError("native engine returned invalid score")
        else:
            verdict = "pass" if score >= self.thresholds[criterion.id] else "fail"
        return Judgment(
            case_id=case.id,
            criterion_id=criterion.id,
            verdict=verdict,
            rationale=f"Native {self.project} dimension {criterion.id}: score={score}; "
            f"explicit threshold={self.thresholds[criterion.id]}. "
            + report.get("explanations", {}).get(criterion.id, ""),
            evidence=report.get("evidence", []),
        )


class DomainRouter:
    """Explicit routing by a caller-provided classifier; never average domain scores."""

    def __init__(self, classifier, routes: dict):
        self.classifier, self.routes = classifier, routes

    def evaluate(self, case, criterion):
        self.last_usage = {}
        domain = self.classifier(case)
        if domain not in self.routes:
            raise ValueError("no evaluator for classified domain")
        target = self.routes[domain]
        try:
            return target.evaluate(case, criterion)
        finally:
            self.last_usage = getattr(target, "last_usage", {})
