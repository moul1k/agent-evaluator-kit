# Provisional AI annotations, not human labels — 2026-11-11

At the owner's request, the existing six-case synthetic study was evaluated twice with GPT-6 Luna. Both passes are machine-generated **judge** submissions, not independent human reviewers. No human or adjudication submissions were generated or imported.

| Measurement | Observed |
|---|---:|
| Synthetic candidates | 6, in 3 source groups |
| Model passes per candidate | 2 |
| Valid AI judgments | 12/12 |
| Authored-contract matches | 12/12 |
| Repeated binary verdict agreement | 6/6 pairs |
| Evaluation / recorded telemetry errors | 0 / 0 |
| Input tokens | 3,448 |
| Output tokens | 1,574 |
| Output-token cap per request | 512 |
| Langfuse observations verified | 12/12 |
| Langfuse traces with a categorical score verified | 12/12 |
| Human judgments / human-reference cells | **0 / 0** |

The candidates have analysis/meeting/scheduler domain tags but share one narrow structured numerical-evidence criterion. These results establish a successful integration and repeatability smoke test, not broad cross-domain agent performance or human agreement. Three source groups and repeated judgments are not twelve independent samples.

## What was saved

- Six original per-domain/per-pass judge submissions with verdicts, concise rationales and evidence.
- Annotation origin explicitly marked `ai_generated`, kind `judge`, status `provisional_not_human_validated`.
- Immutable study imports, authored-specification audits, repeated-verdict analysis and an organizer report with human-reference metrics unavailable.
- Runtime token counts, latency and Langfuse trace IDs. Cloud tracing used metadata/verdicts/usage only; full rationales and candidate artifacts remain local.

The first immediate read-back saw 10 observations and 8 score-bearing traces. One bounded later read found all 12. The initial verification file was preserved; a separate follow-up records successful ingestion. No extra model calls were made to resolve the ingestion delay.

[Open one verified synthetic trace](https://us.cloud.langfuse.com/project/cmumzkxxx03qkad0cmba56nvn/traces/14e65f010fbc0f62f9436f66ae6dc734) (requires Langfuse project access).

## Reproducing the run

```bash
python scripts/run_ai_annotation_pilot.py artifacts/my-study artifacts/ai-pilot --run-id unique-run-name --credentials /path/openai-key.docx --langfuse-credentials /path/langfuse-keys.txt --max-calls 12 --contracts /path/authored-contracts.json
```

The runner checks the total two-pass plan against the call cap before provider setup, rejects reused run identities, caps each response at 512 tokens and stops launching model evaluations after an error. The cap counts evaluator calls, not a dollar budget. Credentials stay in process memory and are not saved to source control. Use a fresh output directory and run identity.

For a bounded read-only follow-up (no model calls):

```bash
python scripts/run_ai_annotation_pilot.py artifacts/my-study artifacts/ai-pilot --run-id unique-run-name --langfuse-credentials /path/langfuse-keys.txt --verify-only
```

`--contracts` is optional and used only after judgments, never included in model inputs. Without it, there is no authored match-rate result. The read-back queries are bounded and may be incomplete under pagination or ingestion delay; never infer successful ingestion solely from local trace IDs.

## Actual human annotation remains the next step

AI drafts may help a person inspect evidence after an independent review, but they cannot replace a human reference study. Have the reviewers complete their assigned blind pages before showing them these model predictions. Keep their initial critiques and independently selected verdicts. Only then compare the AI judgments with human consensus/adjudication.

The study importer now rejects machine-origin exports submitted as human annotations, even if the kind field is changed to `human`. This is an accidental-mislabeling safeguard, not authentication: a dishonest editor could remove provenance fields. Real reviewer identity and independence remain organizer responsibilities.
