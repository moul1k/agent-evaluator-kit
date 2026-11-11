# Running a human-calibrated evaluator study

The study runner connects existing adapters, judges and human comparisons into one reproducible workflow. It does not collect real human labels automatically, invent consensus, or run paid models during planning/reporting.

For optional machine-generated drafts, see the [AI annotation pilot](ai-annotation-pilot-2026-11-11.md). These enter the study only as judge predictions, not human references. Machine-origin metadata is rejected on human imports.

## API-free demonstration

```bash
agent-eval study demo artifacts/study-demo
```

This creates six synthetic candidates with three domain tags, six assigned review pages (two reviewers per domain), and `initial-report/index.html`. There are **zero human judgments and zero human references**. The demonstration uses one narrow numerical criterion, not three complete domain evaluations. It is ready for a person to review, not a completed validation study.

## 1. Freeze a real study

Prepare canonical cases and a versioned rubric using the existing adapter/import tools. Define a StudyPlan JSON (see examples/study-plan.json for the small demo shape):

- `domain_by_group`: one domain for every eligible source group in the chosen split.
- `criteria_by_domain`: only criteria that apply to that domain. They must exist in the source rubric.
- `groups_per_domain`: source groups sampled per domain; default 15. Every variant of a chosen group is included.
- `reviewers`: distinct pseudonymous reviewer IDs. `reviews_per_group` defaults to 2 and must be at least 2.
- `adjudicators`: separate registered identities allowed to resolve disagreements.
- `groups_per_batch`: a whole-group batch size, not a case-count or time estimate.
- `split`, `seed`, `id`, `version` and the research purpose.

```bash
agent-eval study create cases.jsonl rubric.json plan.json artifacts/calibration-v1
```

Planning fails if any configured domain has fewer groups than requested; it never quietly shrinks the quota. Sampling is seeded, uniform within domain, and independent of model scores/expected labels. Case and criterion cell counts may differ between domains because group variants and rubrics differ. Reviewer assignment greedily balances criterion-cell workload, not estimated cognitive difficulty.

Related variants remain in one group/split and receive the same reviewer cohort. Each review page contains only its assigned cases and applicable rubric subset, with randomized case order, no other reviewers' labels, and no judge submissions. Use opaque candidate IDs: names such as `bad-example` can reveal intended labels.

Outputs:

```text
study.json                    frozen protocol, sample, assignments and study hash
cases.jsonl + rubric.json     complete selected study, frozen
domains/domain-0001/...      domain-specific frozen inputs for judges
reviews/batch-0001.html      assigned offline review page
imports/<sha256>.json        exact original exported submission bytes
events/000001.json           append-only import/replacement receipt
```

Create a new study directory/version when changing the rubric, sample or protocol. Do not edit frozen inputs or replace old hashes to force compatibility.

## 2. Collect independent reviews

Privately give each reviewer only their assigned HTML files. The page asks for an initial observation before revealing rubric questions. Reviewers may explicitly state that they found no issue. That initial text is preserved separately from later critiques about the rubric. This helps surface omissions/ambiguities; it does not automatically establish whether a rubric is valid.

The page supports partial export/resume, verdict/rationale/evidence, study/batch metadata and assigned reviewer ID. Selected verdicts require rationale before export. Export before closing: there is no automatic saving.

```bash
agent-eval study ingest-human artifacts/calibration-v1 batch-0001 reviewer-export.json
agent-eval study status artifacts/calibration-v1
```

The importer checks assigned identity, kind, case/criterion membership, dataset/rubric hashes and study/batch metadata. It rejects marked scripted-demo labels. An identity field is **not authentication**: the organizer must ensure real reviewers work independently. Critique-first is an ordinary UI workflow, not secure blinding; rubric text exists inside the HTML source and can be inspected. No annotations are uploaded to Langfuse by the study importer.

Progress counts judgments separately from initial critiques. A batch is complete only when every assigned cell and initial critique is present. Partial labels can still contribute to a reference when the protocol's required number of reviewers agree; missing initial text keeps the batch incomplete but does not erase a label.

## 3. Import revised snapshots deliberately

```bash
agent-eval study ingest-human artifacts/calibration-v1 batch-0001 revised-export.json --replace
```

Replacement is a **whole snapshot**, not a merge of missing labels from old exports. The old raw bytes and receipt are retained. Same-byte repeat imports are idempotent. The new event points to its predecessor and the replaced blob. This permits retractions without silently keeping an old judgment. Losing labels in a partial replacement reduces the progress count.

Imports use an exclusive lock and publish each event atomically. If a process crashes leaving `.import.lock` or a `.pending` event, stop writers, inspect the files and preserve a backup before manual recovery. Do not blindly delete a live lock. Hashes detect accidental changes; they are not signatures, an access-control boundary, or protection against an organizer rewriting/truncating the entire history.

## 4. Run and import evaluators

Use the domain-specific exports so each judge sees the right criteria:

```bash
agent-eval run artifacts/calibration-v1/domains/domain-0001/cases.jsonl artifacts/calibration-v1/domains/domain-0001/rubric.json artifacts/judge-analysis.json judge-v1 --plugin openai --model gpt-6-luna --max-calls 30
agent-eval study add-judge artifacts/calibration-v1 artifacts/judge-analysis.json --domain analysis
```

The run is an ordinary optional paid model invocation; the study commands themselves are API-free. Existing credential-loading, Langfuse, call limits and deterministic/native/subprocess plugins remain available. Check each domain.json to identify its name; numeric directory order is not a domain contract.

Use the same evaluator ID across domains only when you intend one named evaluation system; retain configuration fingerprints for differing domain plugins. Root-study judge imports are supported without `--domain` only when all judgments use applicable criteria. Mixing whole-study and per-domain snapshots for one evaluator is rejected to avoid overlapping predictions. Judge IDs cannot reuse human identities.

The importer validates each original domain/batch bundle and archives the original bytes. Reports then perform explicit, controlled normalization into domain comparison views, retaining source blob hashes. This is not permission to edit submission provenance manually.

## 5. Adjudicate disagreements explicitly

An adjudication is a standard Submission of kind `adjudication`, from a registered adjudicator, with `metadata.adjudication_reason` and evidence/rationales for its judgments. Use the full selected-study hashes, or a domain bundle with `--domain`. It represents a real review decision; do not generate it just to remove unresolved cells.

```bash
agent-eval study adjudicate artifacts/calibration-v1 adjudication.json --domain analysis
```

Unanimous binary votes from the protocol's required reviewer count establish a human reference. A registered explicit adjudication can resolve it. Disagreement, insufficient votes, conflicting adjudications and nonbinary votes remain unresolved. Model agreement is never used to manufacture a reference. Original reviewer labels remain archived after adjudication.

## 6. Produce a report snapshot

```bash
agent-eval study report artifacts/calibration-v1 artifacts/calibration-report-01
```

Open index.html. Reports contain batch progress, frozen protocol, pre-rubric critiques, per-domain human comparisons and queues of disagreements/errors/missing predictions. Provider usage, latency and trace IDs are retained when judges reported them; missing usage is marked unavailable rather than treated as measured zero spend. There is no universal price estimate for arbitrary plugins.

Per-domain metrics include failure precision/detection, answered false acceptance/rejection, abstention, missingness, coverage, human pair agreement and group-bootstrap uncertainty. Reference-cell denominators are not independent scenario counts. No pooled cross-domain accuracy is computed. With zero human references, accuracy-like metrics stay unavailable even if model calls succeeded or synthetic contracts match perfectly.

Generated reports are new snapshots and refuse overwrite. They contain reviewer critiques and may contain private source content in domain review queues: keep them under ignored artifacts/ and share deliberately. Do not publish actual study data or labels in the public repository without consent.

## Suggested next research action

Run a small calibration batch, have two people independently review it, then classify disagreements as rubric scope, evidence sufficiency, reference-specification problems or judge-application errors. Revise on development data, freeze the next version, and test fresh held-out source groups. This release packages that workflow; it does not claim the human study has already happened.
