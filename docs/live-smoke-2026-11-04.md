# Live integration smoke test — 2026-11-04

This tests installation, credential loading, model judgments and hosted instrumentation, not representative cross-domain agent quality.

| Measurement | Observed |
|---|---:|
| Model | GPT-6 Luna |
| Authored synthetic judgments | 6 |
| Matching expected verdicts | 6/6 |
| False acceptances / rejections | 0 / 0 |
| Input tokens | 1,724 |
| Output tokens | 853 |
| Output cap per request | 512 |
| Provider evaluation errors | 0 |
| Recorded telemetry errors | 0 |
| Hosted observations independently retrieved | 6/6 |
| Hosted categorical scores independently retrieved | 6/6 |

The same narrow numerical-evidence rubric was applied to six synthetic cases with analysis/scheduler/meeting domain tags. These are not six real agents or six independent meetings, and labels were authored, not independently human validated. No private transcript was used. Runtime credentials were loaded from the owner's supplied files without committing them.

The first read-back used the deprecated trace endpoint and returned HTTP 410. The integration was changed to Observations API v2; existing observations were retrieved without rerunning any model calls. Scores were separately verified through Scores API v3 with subject fields. The immutable original submission retains the initial failed verification; a separate local report records the later successful check.

[View a verified synthetic trace](https://us.cloud.langfuse.com/project/cmumzkxxx03qkad0cmba56nvn/traces/303f21a94f27acf30c49b0279600050c) (requires project access).

Local ignored records: `artifacts/luna-live-20261104.json`, `artifacts/luna-live-audit-20261104.json`, `artifacts/luna-ingestion-verification-20261104.json`. The public-safe summary contains no API keys or transcript data.
