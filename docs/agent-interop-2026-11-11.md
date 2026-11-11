# External SDK agent interoperability — 2026-11-11

## Scope

We executed three separately orchestrated, framework-backed **test agents**, using real provider calls and native SDK tool loops. They were built for this experiment, not independently authored production applications. This establishes compatibility at the SDK/artifact boundary, not universal agent reliability or an external-application audit.

| Runtime | Test agent | Successful live runs | Native output handled |
|---|---|---:|---|
| OpenAI Agents SDK 0.20.0 | Inventory lookup | 2 | RunResult with typed Pydantic final_output |
| LangGraph 1.2.20 / langchain-openai 1.7.4 | Support-ticket lookup | 2 | State dictionary containing native message objects; sync and async invocation |
| smolagents 1.26.0 | Invoice lookup | 1 after configuration fix | ToolCallingAgent final_answer result |

OpenAI client 2.54.0 and Langfuse 4.18.0 were used in an isolated Windows/Python 3.13 environment. The original package environment was not upgraded. The pip resolver selected Agents SDK 0.20.0 within the toolkit's OpenAI-client compatibility constraint; this is not a test of every newer SDK release.

Only synthetic read-only in-memory tools were available. No shell, browser, mail, filesystem tool, real calendar or production data was exposed to the agents. Native OpenAI SDK tracing and LangSmith tracing were disabled; evaluator observations used the owner's configured Langfuse project.

## Actual results, including failures

The first attempt captured 4/6 agent runs: both inventory and both support cases. Both smolagents runs failed with provider HTTP 400 responses. A stop-removal-only attempt also failed. A bounded diagnostic identified `reasoning_effort` as the rejected parameter. A low-effort attempt failed too. The final working configuration used **reasoning_effort=none** for Chat Completions tool calls, with the optional stop parameter omitted defensively. One focused invoice case then succeeded.

The confirmed API restriction is documented in the [GPT-6 Luna model reference](https://developers.openai.com/api/docs/models/gpt-6-luna): Chat Completions function calling requires none reasoning effort. We did not establish that stop removal alone was necessary; removing it alone did not fix the failure. No upstream dependency source was patched.

Across the attempt directories there were 13 attempted agent executions: five captured successfully and eight did not. One failed execution was prevented by the local diagnostic request cap. Seven provider requests returned HTTP 400. Failures remain in their original local artifacts; the successful follow-up does not replace them.

## Evaluator checks

For each of the five captured outputs, we constructed three candidates:

1. The original captured answer, compared against independently owned synthetic tool truth.
2. A corrupted field (wrong count/total or ticket status).
3. The answer with final-state evidence withheld.

This produced **15 candidates in five source groups**, evaluated by both a deterministic structured-state checker and GPT-6 Luna:

| Check | Deterministic evaluator | Model judge |
|---|---:|---:|
| Authored/oracle expectation matches | 15/15 | 15/15 |
| Original answers matched verified tool truth | 5/5 | 5/5 |
| Corrupted outputs rejected | 5/5 | 5/5 |
| Missing state produced insufficient_context | 5/5 | 5/5 |
| False acceptances / false rejections | 0 / 0 | 0 / 0 |

Original-control references used exact dictionary equality against the synthetic ledger, not the deterministic evaluator's own returned verdict. Corruption and missing-evidence expectations were separately specified. These narrow specifications are not independent human judgments or a general task-quality rubric. The same base model generated agent outputs and served as model judge, so model errors could be correlated.

## Usage and hosted traces

- **32 provider requests** across all attempts, within the original total cap of 36; 25 successful responses and seven HTTP 400 responses.
- Reported successful-response usage: **8,794 input tokens and 2,183 output tokens**. This is token accounting, not a billing statement; cached-input/write prices and unreported failed-request usage are not inferred.
- Each request had an explicit 512-output-token cap; HTTP hooks enforced a shared count/model/endpoint/body-size boundary and halted subsequent requests on quota/authentication errors.
- **30/30 evaluator observations and score-bearing traces** were retrieved through supported Langfuse APIs after a bounded follow-up. Immediate read-back was incomplete due to ingestion delay.

These are evaluator-layer traces, not a claim of complete automatic tracing of every SDK's internal model/tool spans. Native result types, message artifacts and actual tool-call logs were retained locally. Cloud export used metadata/verdicts/usage, not full candidate content.

[Example verified evaluation trace](https://us.cloud.langfuse.com/project/cmumzkxxx03qkad0cmba56nvn/traces/04087797a690cb9ccab41ceefea71542) (requires project access).

## Reproduce from a checkout

```bash
python -m venv .venv
# Activate the environment, then:
pip install -e ".[dev,openai,langfuse,interop]"
python scripts/run_agent_interop.py artifacts/new-interop --credentials /path/openai-key.docx --langfuse-credentials /path/langfuse-keys.txt --request-cap 36
```

The current script defaults to the corrected smolagents settings. `--framework smolagents --cases-per-framework 1` restricts the scope. Always use a new output directory. A request cap permits a partial run; it does not guarantee enough budget for every agent and evaluator call. This helper is not a network sandbox or dollar-cost limiter for arbitrary agents.

Read back existing evaluator IDs without model calls:

```bash
python scripts/run_agent_interop.py artifacts/new-interop --langfuse-credentials /path/langfuse-keys.txt --verify-only
```

The raw evidence is ignored locally under `artifacts/agent-interop-20261111/`, `artifacts/agent-interop-smol-fixed-20261111/`, `artifacts/agent-interop-smol-diagnostic-20261111/`, `artifacts/agent-interop-smol-compatible-20261111/` and `artifacts/agent-interop-smol-function-calling-20261111/`. Names reflect the chronological hypotheses; only the last smolagents attempt actually succeeded.

## What improved in the toolkit

The expanded software suite passed **119 tests**, including the three actual-SDK offline checks and both pinned upstream engine checks. Wheel and source builds succeeded. The new CI job runs SDK result/loop tests with a mock transport and no model credits; remote CI completion must be checked separately.

- Dependency-free adapters in `agent_eval.framework_outputs` for typed SDK results, LangGraph messages and smolagents results.
- Explicit rejection of incomplete LangGraph states ending in a tool/user message or pending tool call.
- A narrow `StructuredStateEvaluator` with evidence-aware abstention.
- Shared HTTP request accounting that retains status/usage and safe error parameter identifiers, not credentials/prompts.
- Optional offline tests with real SDK types and a mock-transport smolagents tool loop, protecting the none-effort/omitted-stop settings without paid CI calls.

The user's six earlier human calibration annotations were not used as references for these new cases and were not changed. There are no new human labels or inter-rater agreement results from this experiment.

Current script exits nonzero for generation errors or authored smoke mismatches; read-only verification exits 2 if ingestion is unconfirmed. Results are saved before exit. The earlier exploratory script versions returned their failure records without this exit-code gate, so their zero process status must not be read as an all-agent pass.

Primary API guides: [OpenAI Agents quickstart](https://developers.openai.com/api/docs/guides/agents/quickstart?lang=python), [LangGraph quickstart](https://docs.langchain.com/oss/python/langgraph/quickstart), [smolagents guided tour](https://huggingface.co/docs/smolagents/guided_tour).
