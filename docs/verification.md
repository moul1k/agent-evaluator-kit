# Verification record — 2026-11-04

## Study runner update — 2026-11-11

- **92 tests passed**, including both pinned native-engine integration checks. Without upstream checkouts, the two native checks skip explicitly.
- Frozen planning, group-balanced sampling, scoped review pages, partial/revised imports, byte-preserving archives, reviewer checks, critique progress, disagreement/adjudication and per-domain reports are covered.
- Tested a three-reviewer protocol: two votes do not prematurely create a reference.
- API-free CLI smoke: created six review batches, ran/imported a numerical judge for one domain, and generated a report with zero human references in all domains. No human labels were fabricated.
- Browser-checked the offline page: an empty initial critique blocks rubric reveal; adding an initial critique reveals criteria; a selected verdict without rationale blocks export. The browser test was not exported/imported as a human annotation.
- No paid model calls or new credential use were required for this update. Existing Langfuse-enabled judge runs remain compatible with the domain exports.
- See [study runner guide](study-runner.md) for commands, provenance normalization, privacy and offline identity limitations.

## Follow-up integration verification

The three-project harmony audit subsequently passed **65 tests**, including actual execution of both pinned native grading engines. See [capability matrix and integration checks](three-project-integration.md). Model calls were not needed for this native-engine audit. A separate CI job now checks the bridges against pinned checkouts; local success is not a claim of remote CI completion.

The later plug-and-play update supersedes the initial tracing limitation below: **6/6 live GPT-6 Luna observations and 6/6 categorical scores were retrieved using supported APIs**. See [live smoke results](live-smoke-2026-11-04.md). The updated local test suite passes **56 tests**. New integration APIs cover callable capture, configurable log mappings, hybrid routing, runtime credential loading, usage, request limits and telemetry-failure isolation. The initial record is retained below for provenance.

Environment: Windows, Python 3.13.7, isolated project virtual environment. Exact installed dependency snapshot: `requirements-tested.txt` (Windows verification snapshot, not a universal lockfile).

## Completed

- Editable installation of package with dev/OpenAI/Langfuse extras succeeded.
- Ruff checks passed.
- **35 tests passed**; JUnit saved locally under ignored artifacts/.
- Wheel and source distribution built successfully using hatchling.
- Installed `agent-eval` CLI help, demo, prepare and authored-audit commands exercised.
- Six original synthetic cases: structured numerical checker 6/6 authored matches, zero false acceptances; always-pass control 3/6 matches, three false acceptances.
- Negative-control audit gate exited **1**, as expected.
- Mocked Langfuse client tests confirmed observation metadata, categorical scoring, content omission and flush behavior.
- Mocked OpenAI structured-response adapter tests passed. **No paid model calls made for this extraction.**
- Scheduling plugin tests cover adjacent intervals, actual overlaps, independent attendees, blocked periods, fixed days, earliest starts, deadline days, missing/duplicate/unknown assignments and malformed times.

## Live tracing status — verification blocked by rate limiting

Using the owner's existing credentials, a synthetic metadata-only demo authenticated and generated 12 local Langfuse trace IDs with no recorded SDK scoring errors. SDK flush returned. However, backend trace retrieval returned **HTTP 429** for the requested IDs. Further verification was stopped. **Backend ingestion and score visibility are NOT confirmed.** The SDK can suppress exporter failures, so local IDs alone do not establish successful delivery.

First attempted trace ID: `32b1076e401d37163d94633589b375ba`. The full attempt and bounded ingestion-check reports remain in ignored `artifacts/cloud-smoke/`. No transcript content or model rationales were sent by the configured tracer.

Recheck the Langfuse project's usage/rate limits and dashboard before claiming hosted trace delivery. After access recovers, run a new synthetic `agent-eval demo artifacts/recheck --langfuse` and verify its trace IDs and categorical scores. No repeated background retries are scheduled.

## Not claimed

- Remote CI success is not inferred from local tests; inspect GitHub Actions separately.
- No real-agent executions or new cross-domain model-accuracy study were run here.
- No independent human labels collected.
- No full parity with the upstream domain engines, resolved-correction engine, or universal cost accounting.
- Collaborator code redistribution permission remains outstanding; source attribution documents the original-implementation/adapter boundary.
