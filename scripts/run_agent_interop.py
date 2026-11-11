"""Live SDK interoperability benchmark, with synthetic tools and shared request caps.

These are independently orchestrated test agents built with three external SDKs,
not independently authored production applications. No human labels are generated.
"""

import argparse
import asyncio
import json
import os
import time
from datetime import UTC, datetime, timedelta
from importlib.metadata import version
from pathlib import Path

import httpx
from openai import AsyncOpenAI, OpenAI
from pydantic import BaseModel

from agent_eval import Criterion, Rubric, acapture, bundle_from_cases, capture
from agent_eval.audit import Contract, audit
from agent_eval.config import load_credentials
from agent_eval.demo import write_json
from agent_eval.evaluators import OpenAIEvaluator
from agent_eval.framework_outputs import langgraph_output, openai_agents_output, smolagents_output
from agent_eval.request_budget import RequestBudget
from agent_eval.runner import run
from agent_eval.state_check import StructuredStateEvaluator
from agent_eval.tracing import LangfuseTracer

MODEL = "gpt-6-luna"


def sdk_agent(client, http_client, request, calls):
    from agents import Agent, ModelSettings, OpenAIResponsesModel, RunConfig, Runner, function_tool

    class StockAnswer(BaseModel):
        sku: str
        available: int

    @function_tool
    def stock_lookup(sku: str) -> dict:
        """Read the synthetic inventory count for a product SKU."""
        result = {"sku": sku, "available": {"R7": 24, "Z0": 0}[sku]}
        calls.append({"tool": "stock_lookup", "arguments": {"sku": sku}, "result": result})
        return result

    agent = Agent(
        name="Inventory agent",
        model=OpenAIResponsesModel(MODEL, client),
        instructions="Use stock_lookup to obtain the requested SKU's current count. "
        "Do not guess or change the data. Return exactly sku and available.",
        tools=[stock_lookup],
        output_type=StockAnswer,
        model_settings=ModelSettings(max_tokens=512, store=False),
    )
    return Runner.run_sync(
        agent, request["message"], max_turns=3, run_config=RunConfig(tracing_disabled=True)
    )


def graph_agent(http_client, async_http, calls):
    from langchain_core.messages import SystemMessage, ToolMessage
    from langchain_core.tools import tool
    from langchain_openai import ChatOpenAI
    from langgraph.graph import END, START, MessagesState, StateGraph

    @tool
    def ticket_lookup(ticket_id: str) -> dict:
        """Read the synthetic support ticket's current status and assigned queue."""
        result = {
            "ticket_id": ticket_id,
            "status": {"T1": "open", "T2": "closed"}[ticket_id],
            "queue": "billing",
        }
        calls.append(
            {"tool": "ticket_lookup", "arguments": {"ticket_id": ticket_id}, "result": result}
        )
        return result

    llm = ChatOpenAI(
        model=MODEL,
        max_tokens=512,
        max_retries=0,
        timeout=60,
        use_responses_api=True,
        store=False,
        http_client=http_client,
        http_async_client=async_http,
    ).bind_tools([ticket_lookup])
    prompt = "Use ticket_lookup for the requested ticket. Return ONLY JSON with ticket_id, status, queue."

    def decide(state):
        return {"messages": [llm.invoke([SystemMessage(content=prompt), *state["messages"]])]}

    async def adecide(state):
        return {
            "messages": [await llm.ainvoke([SystemMessage(content=prompt), *state["messages"]])]
        }

    def tools(state):
        messages = []
        for call in state["messages"][-1].tool_calls:
            value = ticket_lookup.invoke(call["args"])
            messages.append(ToolMessage(content=json.dumps(value), tool_call_id=call["id"]))
        return {"messages": messages}

    def route(state):
        return "tools" if state["messages"][-1].tool_calls else END

    graph = StateGraph(MessagesState)
    from langchain_core.runnables import RunnableLambda

    graph.add_node("agent", RunnableLambda(decide, afunc=adecide))
    graph.add_node("tools", tools)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", route)
    graph.add_edge("tools", "agent")
    return graph.compile()


def smol_agent(http_client, request, calls, *, omit_stop=True):
    from smolagents import OpenAIModel, ToolCallingAgent, tool
    from smolagents.models import REMOVE_PARAMETER

    @tool
    def invoice_lookup(invoice_id: str) -> dict:
        """Read the verified invoice total in cents.

        Args:
            invoice_id: Identifier of the synthetic invoice.
        """
        result = {"invoice_id": invoice_id, "total_cents": {"I1": 875, "I2": 0}[invoice_id]}
        calls.append(
            {"tool": "invoice_lookup", "arguments": {"invoice_id": invoice_id}, "result": result}
        )
        return result

    model = OpenAIModel(
        model_id=MODEL,
        api_key=os.environ["OPENAI_API_KEY"],
        client_kwargs={"http_client": http_client, "max_retries": 0, "timeout": 60},
        max_completion_tokens=512,
        retry=False,
        store=False,
        reasoning_effort="none",
        **({"stop": REMOVE_PARAMETER} if omit_stop else {}),
    )
    agent = ToolCallingAgent(
        tools=[invoice_lookup],
        model=model,
        max_steps=3,
        verbosity_level=-1,
        add_base_tools=False,
        instructions="Use invoice_lookup to get the requested invoice. "
        "Return the dictionary with invoice_id and total_cents "
        "using final_answer. Do not add commentary.",
    )
    result = agent.run(request["message"])
    return result, [{"step_type": type(s).__name__} for s in agent.memory.steps]


def verify(tracer, ids, started):
    options = {"timeout_in_seconds": 10, "max_retries": 0}
    result = {"expected": len(ids), "observations_verified": 0, "scores_verified": 0}
    try:
        now = datetime.now(UTC)
        rows = tracer.client.api.observations.get_many(
            name="agent-evaluator-kit",
            fields="core",
            limit=1000,
            from_start_time=started - timedelta(minutes=1),
            to_start_time=now,
            request_options=options,
        )
        found = {r.trace_id for r in rows.data} & ids
        result["observations_verified"] = len(found)
        scores = tracer.client.api.scores_v3.get_many_v3(
            fields="subject",
            limit=100,
            from_timestamp=started - timedelta(minutes=1),
            to_timestamp=now,
            request_options=options,
        )
        seen = {
            getattr(s.subject, "trace_id", None)
            or (s.subject.id if getattr(s.subject, "kind", None) == "trace" else None)
            for s in scores.data
            if s.subject is not None
        }
        result["scores_verified"] = len(seen & ids)
        result["trace_urls"] = [tracer.client.get_trace_url(trace_id=t) for t in sorted(found)]
    except Exception as exc:
        result.update(error_type=type(exc).__name__, http_status=getattr(exc, "status_code", None))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--credentials", type=Path)
    parser.add_argument("--langfuse-credentials", type=Path)
    parser.add_argument("--request-cap", type=int, default=36)
    parser.add_argument("--cases-per-framework", type=int, choices=[1, 2], default=2)
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument(
        "--framework", action="append", choices=["openai-sdk", "langgraph", "smolagents"]
    )
    parser.add_argument(
        "--omit-smol-stop",
        action="store_true",
        default=True,
        help="Use the SDK's parameter-removal sentinel for GPT-6 stop compatibility",
    )
    parser.add_argument(
        "--keep-smol-stop",
        dest="omit_smol_stop",
        action="store_false",
        help="Diagnostic opt-out of the tested stop-removal setting",
    )
    args = parser.parse_args()
    selected = set(args.framework or ["openai-sdk", "langgraph", "smolagents"])
    load_credentials(args.credentials, args.langfuse_credentials)
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    tracer = LangfuseTracer()
    if args.verify_only:
        plan = json.loads((args.output / "plan.json").read_text())
        ids = set()
        for path in args.output.glob("*-submission.json"):
            data = json.loads(path.read_text())
            ids.update(t["trace_id"] for t in data["metadata"]["traces"])
        result = verify(tracer, ids, datetime.fromisoformat(plan["started_at"]))
        write_json(args.output / "trace-verification-followup.json", result)
        print(json.dumps(result, indent=2))
        if result.get("observations_verified") != len(ids) or result.get("scores_verified") != len(
            ids
        ):
            raise SystemExit(2)
        return
    args.output.mkdir(parents=True, exist_ok=False)
    started = datetime.now(UTC)
    packages = {
        name: version(name)
        for name in (
            "openai-agents",
            "openai",
            "langgraph",
            "langchain-openai",
            "smolagents",
            "langfuse",
        )
    }
    write_json(
        args.output / "plan.json",
        {
            "started_at": started.isoformat(),
            "packages": packages,
            "model": MODEL,
            "request_cap": args.request_cap,
            "max_output_tokens": 512,
            "agent_runs": len(selected) * args.cases_per_framework,
            "planned_candidates": len(selected) * args.cases_per_framework * 3,
            "frameworks": sorted(selected),
            "omit_smol_stop": args.omit_smol_stop,
            "smol_chat_reasoning_effort": "none",
            "scope": "Framework-backed test agents, not third-party production applications",
        },
    )
    budget = RequestBudget(limit=args.request_cap)
    sync_http = httpx.Client(
        timeout=60, event_hooks={"request": [budget.before], "response": [budget.response_hook]}
    )
    async_http = httpx.AsyncClient(
        timeout=60,
        limits=httpx.Limits(max_keepalive_connections=0),
        event_hooks={
            "request": [budget.async_request_hook],
            "response": [budget.async_response_hook],
        },
    )
    async_client = AsyncOpenAI(http_client=async_http, max_retries=0)
    sync_client = OpenAI(http_client=sync_http, max_retries=0)
    rubric = Rubric(
        id="verified-tool-results",
        version="1",
        criteria=[
            Criterion(
                id="result_consistency",
                question="Does the structured answer match verified tool truth?",
                pass_condition="Answer keys and values match verified_result, with numeric tolerance 0.0005. "
                "When verified_result is absent, return insufficient_context.",
                fail_condition="The answer contradicts or omits verified fields. Missing state must abstain.",
            )
        ],
    )
    cases, contracts, generations = [], [], []
    for framework, identifiers in [
        ("openai-sdk", ["R7", "Z0"]),
        ("langgraph", ["T1", "T2"]),
        ("smolagents", ["I1", "I2"]),
    ]:
        if framework not in selected:
            continue
        for number, identifier in enumerate(identifiers[: args.cases_per_framework], 1):
            if budget.halted:
                break
            cid = f"{framework}-{number}"
            calls, t0 = [], time.perf_counter()
            request = {
                "message": f"Look up {identifier} with the provided tool and report its exact fields."
            }
            try:
                if framework == "openai-sdk":
                    raw = {}

                    def invoke(value):
                        result = sdk_agent(async_client, sync_http, value, calls)
                        raw.update(
                            native_type=type(result).__name__,
                            items=[item.to_input_item() for item in result.new_items],
                        )
                        return result

                    case = capture(
                        invoke,
                        request,
                        case_id=cid,
                        group_id=cid,
                        output_adapter=lambda r: {"answer": openai_agents_output(r)},
                    )
                elif framework == "langgraph":
                    graph, raw = graph_agent(sync_http, async_http, calls), {}

                    def invoke(value):
                        result = graph.invoke(
                            {"messages": [("user", value["message"])]}, {"recursion_limit": 5}
                        )
                        raw.update(
                            native_type=type(result).__name__,
                            messages=[m.model_dump(mode="json") for m in result["messages"]],
                        )
                        return result

                    async def ainvoke(value):
                        result = await graph.ainvoke(
                            {"messages": [("user", value["message"])]}, {"recursion_limit": 5}
                        )
                        raw.update(
                            native_type=type(result).__name__,
                            messages=[m.model_dump(mode="json") for m in result["messages"]],
                        )
                        return result

                    def adapt(result):
                        return {"answer": langgraph_output(result, parse_json=True)}

                    case = (
                        capture(invoke, request, case_id=cid, group_id=cid, output_adapter=adapt)
                        if number == 1
                        else asyncio.run(
                            acapture(
                                ainvoke, request, case_id=cid, group_id=cid, output_adapter=adapt
                            )
                        )
                    )
                else:
                    raw = {}

                    def invoke(value):
                        result, memory = smol_agent(
                            sync_http, value, calls, omit_stop=args.omit_smol_stop
                        )
                        raw.update(native_type=type(result).__name__, memory_steps=memory)
                        return result

                    case = capture(
                        invoke,
                        request,
                        case_id=cid,
                        group_id=cid,
                        output_adapter=lambda r: {"answer": smolagents_output(r, parse_json=True)},
                    )
                if not calls:
                    raise ValueError("agent returned without executing the required lookup")
                # Independently owned synthetic truth, not copied from the assistant's claim.
                expected = (
                    {"sku": identifier, "available": {"R7": 24, "Z0": 0}[identifier]}
                    if framework == "openai-sdk"
                    else {
                        "ticket_id": identifier,
                        "status": {"T1": "open", "T2": "closed"}[identifier],
                        "queue": "billing",
                    }
                    if framework == "langgraph"
                    else {"invoice_id": identifier, "total_cents": {"I1": 875, "I2": 0}[identifier]}
                )
                case.tool_trace, case.final_state = calls, {"verified_result": expected}
                write_json(args.output / f"{cid}-native.json", raw)
                for variant in ("original", "corrupted", "missing-state"):
                    candidate = case.model_copy(deep=True)
                    candidate.id += "-" + variant
                    if variant == "corrupted":
                        field = (
                            "available"
                            if framework == "openai-sdk"
                            else "status"
                            if framework == "langgraph"
                            else "total_cents"
                        )
                        candidate.output["answer"][field] = (
                            "unknown" if field == "status" else expected[field] + 1
                        )
                    elif variant == "missing-state":
                        candidate.final_state = None
                    cases.append(candidate)
                    reference = (
                        "insufficient_context"
                        if variant == "missing-state"
                        else "fail"
                        if variant == "corrupted"
                        else "pass"
                        if candidate.output["answer"] == expected
                        else "fail"
                    )
                    contracts.append(
                        Contract(
                            case_id=candidate.id,
                            criterion_id="result_consistency",
                            expected=reference,
                            defect=variant,
                        )
                    )
                generations.append(
                    {
                        "case_id": cid,
                        "framework": framework,
                        "status": "captured",
                        "tool_calls": len(calls),
                        "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
                    }
                )
            except Exception as exc:
                generations.append(
                    {
                        "case_id": cid,
                        "framework": framework,
                        "status": "error",
                        "error_type": type(exc).__name__,
                    }
                )
            write_json(args.output / f"{cid}-generation.json", generations[-1])
            print(json.dumps(generations[-1]), flush=True)
    write_json(args.output / "generations.json", generations)
    audits, traces = {}, set()
    if cases:
        bundle = bundle_from_cases(cases, rubric)
        write_json(args.output / "bundle.json", bundle)
        write_json(args.output / "contracts.json", [c.model_dump() for c in contracts])
        for name, evaluator in [
            ("state-check", StructuredStateEvaluator()),
            ("model-judge", OpenAIEvaluator(MODEL, client=sync_client, max_output_tokens=512)),
        ]:
            submission = run(bundle, evaluator, name, tracer=tracer, max_calls=18)
            write_json(args.output / f"{name}-submission.json", submission.model_dump(mode="json"))
            audits[name] = audit(bundle, submission, contracts)
            traces.update(t["trace_id"] for t in submission.metadata["traces"])
        write_json(args.output / "audits.json", audits)
    write_json(args.output / "provider-requests.json", budget.rows)
    verification = verify(tracer, traces, started) if traces else {"expected": 0}
    write_json(args.output / "trace-verification.json", verification)
    summary = {
        "agent_runs": generations,
        "captured_candidates": len(cases),
        "audits": {
            n: {
                k: r[k]
                for k in ("cells", "match_rate", "false_acceptances", "false_rejections", "missing")
            }
            for n, r in audits.items()
        },
        "provider_requests": len(budget.rows),
        "input_tokens": sum(r.get("input_tokens", 0) for r in budget.rows),
        "output_tokens": sum(r.get("output_tokens", 0) for r in budget.rows),
        "trace_verification": verification,
        "packages": packages,
        "human_validation": "none for these new cases; existing human labels unchanged",
    }
    write_json(args.output / "summary.json", summary)
    print(json.dumps(summary, indent=2))
    if any(row["status"] == "error" for row in generations) or any(
        result["match_rate"] < 1 for result in audits.values()
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
