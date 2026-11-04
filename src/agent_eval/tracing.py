"""Explicit opt-in cloud export. By default only hashes and verdicts leave the host."""

from contextlib import contextmanager


class LangfuseTracer:
    def __init__(self, client=None, include_content=False):
        if client is None:
            import os

            from langfuse import Langfuse

            if not all(os.environ.get(k) for k in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY")):
                raise ValueError("Langfuse credentials required")
            client = Langfuse()
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

    def record(self, span, judgment):
        span.update(
            output=judgment.model_dump() if self.include_content else {"verdict": judgment.verdict}
        )
        self.client.create_score(
            trace_id=span.trace_id,
            observation_id=span.id,
            name=judgment.criterion_id,
            value=judgment.verdict,
            data_type="CATEGORICAL",
        )

    def flush(self):
        self.client.flush()
