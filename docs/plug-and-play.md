# Connecting agents without rewriting them

The integration boundary is JSON artifacts, not an agent framework. Most agents that expose a callable or export JSON/text outputs can connect through these adapters. This does **not** mean every task has an automatic trustworthy rubric: domain-specific criteria and evidence must still be supplied.

Native output adapters and real SDK/tool-loop tests now cover specific OpenAI Agents SDK, LangGraph and smolagents versions. See the [interoperability results and failure history](agent-interop-2026-11-11.md). This does not establish compatibility with every application built on those frameworks.

```python
from agent_eval.framework_outputs import openai_agents_output, langgraph_output, smolagents_output

# Supply these as output_adapter callbacks to capture/acapture:
sdk_adapter = lambda result: {"answer": openai_agents_output(result)}
graph_adapter = lambda state: {"answer": langgraph_output(state, parse_json=True)}
smol_adapter = lambda result: {"answer": smolagents_output(result, parse_json=True)}
```

Tool traces and verified final state still need independent capture. Output conversion alone never proves a tool executed or a real operation succeeded.

## 1. Existing logs: configuration-only import

```bash
agent-eval import-records examples/agent-records.jsonl examples/field-map.json artifacts/imported.jsonl
```

Field maps use JSON pointers, including array indices and escaped keys. Missing mapped fields are errors, not silently empty evidence. Only explicitly selected fields are imported. String/list inputs are wrapped under `input.value`. Never map a parent object that contains human labels, reference answers or secrets into an ordinary judge input. The toolkit cannot infer sensitive content inside arbitrary JSON.

This covers custom REST/MCP logs, agent runners, and framework export formats as long as the selected fields are JSON-serializable. The named transcription/analysis/scheduler adapters remain available.

## 2. Existing Python agents

```python
from agent_eval import capture, acapture

case = capture(
    agent.invoke,
    {"messages": messages},
    case_id="candidate-1",
    group_id="source-request-1",
    output_adapter=lambda result: result["messages"][-1].content,
)

# For asynchronous agents:
case = await acapture(
    agent.ainvoke,
    {"messages": messages},
    case_id="candidate-2",
    group_id="source-request-1",
    output_adapter=lambda result: result["messages"][-1].content,
)
```

These are interface recipes, **not tested native integrations with every SDK**. Wrap other signatures with a lambda. Use output_adapter to normalize Pydantic models, SDK message objects, file references or other non-JSON values. `capture` performs a real call to your agent; costs/side effects remain the agent's responsibility. Tools and verified final state are never inferred from its final answer. Supply independently captured evidence using `tool_trace` and `final_state`, or attach it before building the bundle. Raw media is not a JSON artifact; represent it with permitted references or a task-specific extraction layer.

`bundle_from_cases(cases, rubric)` builds a hash-validated bundle in memory. The same grouping/leakage checks apply as for JSONL datasets. `python examples/quickstart.py` is a complete API-free executable example.

## 3. Existing evaluators and hybrid routing

```python
from agent_eval import CallableEvaluator, RoutedEvaluator
from agent_eval.evaluators import NumericResultEvaluator, OpenAIEvaluator

judge = RoutedEvaluator(
    {"numerical_evidence": NumericResultEvaluator(), "existing_rule": CallableEvaluator(my_rule)},
    fallback=OpenAIEvaluator("gpt-6-luna"),
)
```

Callable rules receive a case dictionary and criterion dictionary; return verdict/rationale/evidence or a complete Judgment. Subprocess plugins cover non-Python judges without shell interpolation. Unsupported routed criteria abstain if no fallback exists. Do not silently convert arbitrary 0–1 scores to binary labels: explicitly define the threshold in your adapter/rubric. For repeated hybrid runs, pass an explicit configuration with every route's version, model and settings to the runner.

## 4. Runtime credentials and automatic CLI tracing

```powershell
agent-eval run cases.jsonl rubric.json judge.json luna-v1 --plugin openai --model gpt-6-luna --credentials "C:/path/openai api.docx" --langfuse-credentials "C:/path/langfuse keys.txt" --max-calls 20 --max-output-tokens 512 --verify-traces
```

Credentials are read into process memory, never copied into the repository, reports or prompts. Environment values take precedence. TXT and DOCX documents are treated only as credential data; instructions in them are not executed. Automatic host extraction is restricted to known Langfuse Cloud hosts; use LANGFUSE_BASE_URL explicitly for self-hosting.

For the `run` command, tracing automatically enables when both Langfuse keys are configured. `--no-langfuse` overrides this; `--langfuse` requires installed extras and valid configuration. Embedded Python uses an explicit `LangfuseTracer()` passed to `run`. `demo` remains opt-in. `.env.example` is a template, not an auto-loaded secret file.

By default, only identifiers/hashes/verdicts/provider token usage are exported. `--trace-content` additionally sends artifacts/rationales and requires tracing. Avoid PII in identifiers. Model requests use store=False; this is not a claim of zero-retention account policy.

`--max-calls` validates the full case × criterion plan before any requests; default 100. `--max-output-tokens` limits each OpenAI request, not total dollar spend. No automatic retries. HTTP 401/403/429 halt further provider evaluations; errors/skipped cells remain visible. Token counts are recorded locally and in observation metadata; arbitrary third-party plugins must explicitly expose usage. The call limit bounds evaluator invocations, not internal requests hidden inside custom plugins.

`agent-eval doctor --credentials ... --langfuse-credentials ...` prints configuration booleans, never keys. Add `--trace-id ID` for a bounded current-API observation check (last 24 hours). A pending result is not evidence of failure; ingestion may lag. Observation verification does not itself verify scores.

Telemetry entry/exit/score/flush errors do not discard completed judgments. CLI exit 1 indicates recorded evaluation/telemetry errors; exit 2 indicates requested trace verification was not confirmed. `--verify-traces` checks the first successful trace with no retries, not every trace in a large run. Historical raw results are not overwritten when a later verification succeeds.
