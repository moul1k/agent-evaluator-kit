"""HTTP event-hook request cap shared by external SDKs in an integration test.

Records usage/status only, not headers, keys, prompts or response text. This is
a bounded experiment helper, not a monetary billing guarantee or network sandbox.
"""

import json
import re


class RequestBudget:
    def __init__(self, limit=36, max_output_tokens=512, max_body_bytes=24000):
        if min(limit, max_output_tokens, max_body_bytes) <= 0:
            raise ValueError("positive request limits required")
        self.limit, self.max_output_tokens, self.max_body_bytes = (
            limit,
            max_output_tokens,
            max_body_bytes,
        )
        self.rows, self.index, self.halted = [], {}, False

    def before(self, request):
        if self.halted or len(self.rows) >= self.limit:
            raise RuntimeError("shared request budget exhausted or halted")
        if request.url.host != "api.openai.com" or request.url.path not in (
            "/v1/responses",
            "/v1/chat/completions",
        ):
            raise ValueError("unexpected provider endpoint")
        if len(request.content) > self.max_body_bytes:
            raise ValueError("request body exceeds experiment size cap")
        body = json.loads(request.content)
        cap = body.get(
            "max_output_tokens", body.get("max_completion_tokens", body.get("max_tokens"))
        )
        if (
            body.get("model") != "gpt-6-luna"
            or isinstance(cap, bool)
            or not isinstance(cap, int)
            or not 0 < cap <= self.max_output_tokens
        ):
            raise ValueError("explicit model and bounded output tokens required")
        if body.get("stream"):
            raise ValueError("streaming is disabled in this budgeted experiment")
        self.index[id(request)] = len(self.rows)
        reasoning = body.get("reasoning")
        self.rows.append(
            {
                "endpoint": request.url.path,
                "model": body["model"],
                "output_cap": cap,
                "reasoning_effort": body.get(
                    "reasoning_effort",
                    reasoning.get("effort") if isinstance(reasoning, dict) else None,
                ),
            }
        )

    def after(self, response):
        row = self.rows[self.index[id(response.request)]]
        row["status"] = response.status_code
        if response.status_code in (401, 403, 429):
            self.halted = True
        try:
            payload = response.json()
            error = payload.get("error", {})
            if isinstance(error, dict):
                for key in ("code", "param"):
                    value = error.get(key)
                    if isinstance(value, str) and re.fullmatch(
                        r"[A-Za-z_][A-Za-z0-9_.]{0,80}", value
                    ):
                        row["error_" + key] = value
            usage = payload.get("usage", {})
            row.update(
                input_tokens=usage.get("input_tokens", usage.get("prompt_tokens", 0)),
                output_tokens=usage.get("output_tokens", usage.get("completion_tokens", 0)),
            )
        except (ValueError, AttributeError):
            row["usage_unavailable"] = True

    def response_hook(self, response):
        response.read()
        self.after(response)

    async def async_request_hook(self, request):
        self.before(request)

    async def async_response_hook(self, response):
        await response.aread()
        self.after(response)
