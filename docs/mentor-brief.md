# Mentor presentation: from one agent to portable evaluator infrastructure

## Research question

Can we identify when an evaluation criterion is wrong, when the judge applies it incorrectly, and when the evidence is insufficient—across different kinds of agents?

## Architecture

Agent artifacts -> source adapter -> validated JSON case + versioned rubric -> deterministic/model/subprocess evaluator -> typed submission + optional Langfuse observation -> authored-contract audit OR independent-human comparison -> review queue and release gate.

Reference labels never enter the ordinary judge request. The human review bundle does not contain model verdicts. The core has no scheduling, transcription, pandas, or agent-orchestration dependency.

## What changed in this extraction

1. Removed meeting-specific input/output types from the core; introduced arbitrary JSON artifacts and scenario groups.
2. Preserved independent annotation, adjudication, dataset/rubric hashing, uncertainty-aware comparison and repeat analysis.
3. Added three explicit source-format adapters without redistributing unlicensed collaborator code.
4. Added a common Python/subprocess/model runner with categorical Langfuse scores and privacy-default metadata tracing.
5. Added narrow numerical verification, authored-contract auditing, always-pass negative control, required-dimension gates and correction-exercise helper.
6. Added installable package, API-free demo, regression tests and cross-platform CI configuration.

## Five-minute demo

- Run `agent-eval demo artifacts/demo`.
- Open review.html: demonstrate that source evidence is available but expected labels and judge verdicts are hidden.
- Open report.json: numerical checker matches 6/6; always-pass control matches 3/6 and falsely accepts all three bad candidates.
- Run `agent-eval audit ...` on always-pass.json: configured gate exits 1.
- Show the [verified live smoke test](live-smoke-2026-11-04.md): six GPT-6 Luna observations and six categorical scores were retrieved through supported APIs. The initial extraction-time verification returned HTTP 429; the later legacy read returned 410. The observation-based reader now works. Full artifacts stay local by default.
- Explain that this tiny synthetic demo validates plumbing and one narrow property, not cross-domain semantic judgment.

## Earlier findings motivating the design

Historical transcription-project experiments (2026-10-20), NOT new results from this package:

- 264 successful model calls, estimated combined model cost $0.03898805.
- Scoped uncertainty wording improved authored-contract agreement from 26/36 to 36/36.
- Tool final-state context yielded 16/16 matches; output-only context yielded 16/16 expected abstentions.
- Edge audit: 70/72 matches, 36/36 repeat agreements, but two false acceptances of the same wrong UTC date.

These findings motivate scope isolation, evidence-aware abstention, and separating stability from correctness. They do not establish independent human accuracy. Historical private artifacts and transcripts are not migrated or uploaded with this repository.

## Next milestones and acceptance criteria

1. Obtain contributor permission and settle licensing. Review format mappings with Aayush and Srihari.
2. Two independent reviewers label a 10–15-case calibration batch spanning the three domains; include random apparent passes as well as failures. Preserve critiques and adjudicate disagreements.
3. Freeze criterion definitions, plugin versions, data splits and thresholds; collect fresh held-out scenarios per domain.
4. Connect each domain's full deterministic checks; test hybrid versus model-only judging without feeding reference verdicts to either.
5. Report per-domain/dimension false acceptance/rejection, failure detection, coverage/abstention, human agreement, repeat stability, latency and measured provider usage/cost. Use independent scenario clusters for uncertainty.
6. Decide release gates with mentors based on risk, not a convenient mean accuracy. Add bounded paid experiments only after the protocol is agreed.

## Limitations

No independent human study completed; no production validation; adapter compatibility is not equivalent to full agent integration. The demo exercises three domain tags with a shared narrow check, not all semantics of three agents. New runner reports latency but does not yet standardize token/cost accounting across arbitrary provider plugins. CI is configured; a remote CI pass must be observed separately.
