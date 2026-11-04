"""Explicit opt-in cloud export. By default only hashes and verdicts leave the host."""

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta


class LangfuseTracer:
    def __init__(self, client=None, include_content=False):
        if client is None:
            import os

            from langfuse import Langfuse

            if not all(os.environ.get(k) for k in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY")):
                raise ValueError("Langfuse credentials required")
            client = Langfuse(timeout=10)
        self.client, self.include_content = client, include_content
        self.errors = []

    @contextmanager
    def observation(self, metadata, request):
        # Suppress SDK exception recording of provider messages / sensitive artifacts.
        with self.client.start_as_current_observation(
            name="agent-evaluator-kit",
            as_type="evaluator",
            metadata=metadata,
            input=request if self.include_content else None,
        ) as span:
            yield span

    def record(self, span, judgment, usage=None):
        span.update(
            output=judgment.model_dump() if self.include_content else {"verdict": judgment.verdict}
        )
        if usage:
            span.update(metadata={"provider_usage": usage})
        self.client.create_score(
            trace_id=span.trace_id,
            observation_id=span.id,
            name=judgment.criterion_id,
            value=judgment.verdict,
            data_type="CATEGORICAL",
        )

    def flush(self):
        self.client.flush()

    def verify_trace(self, trace_id):
        """One bounded request, no retries. Never infer ingestion from a local ID."""
        try:
            now = datetime.now(UTC)
            observations = self.client.api.observations.get_many(
                trace_id=trace_id,
                fields="core",
                limit=10,
                from_start_time=now - timedelta(days=1),
                to_start_time=now,
                request_options={"timeout_in_seconds": 10, "max_retries": 0},
            )
            matches = [o for o in observations.data if o.trace_id == trace_id]
            return {
                "status": "verified" if matches else "pending",
                "trace_id": trace_id,
                "observation_count": len(matches),
                "scores_verified": False,
            }
        except Exception as exc:
            code = getattr(exc, "status_code", None)
            return {
                "status": "rate_limited" if code == 429 else "unverified",
                "http_status": code,
                "error_type": type(exc).__name__,
            }


@contextmanager
def safe_observation(tracer, metadata, request, errors):
    """Telemetry setup/exit errors must not discard evaluation results."""
    context, span, entered = None, None, False
    if tracer:
        try:
            context = tracer.observation(metadata, request)
            span = context.__enter__()
            entered = True
        except Exception as exc:
            errors.append({"error_type": type(exc).__name__, "phase": "enter"})
    try:
        yield span
    finally:
        if entered:
            try:
                context.__exit__(None, None, None)
            except Exception as exc:
                errors.append({"error_type": type(exc).__name__, "phase": "exit"})
