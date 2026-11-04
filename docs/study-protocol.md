# Human calibration and held-out study

1. Define each criterion's scope, binary failure boundary, missing-evidence policy and examples with mentors/domain owners. Do not silently equate omission with invented facts.
2. Freeze development/test splits at the source-scenario level. All variants and repeated judgments stay in one group. Keep a sampling log; avoid selecting only interesting failures.
3. Create blind review bundles. Two independent humans export their own rationale/evidence and freeform critique. The organizer, not browser identity fields, guarantees independence.
4. Compare labels before revealing model judgments. Resolve disagreements by discussion and explicit adjudication submissions; retain original labels and decision history. Nonbinary or insufficient votes remain unresolved.
5. Separate rubric problems, evidence problems, authored-specification mistakes and judge-application mistakes in the review log. Revise on development data, then freeze a new rubric version.
6. Run frozen evaluators on fresh held-out cases. Log model/configuration fingerprints, prompt versions, latency, usage, errors and traces. No reference labels in judge inputs.
7. Report false acceptance/rejection, failure precision and detection, abstention/missingness, coverage, human agreement and repeat stability by domain/dimension. Report denominators and independent group counts. Cluster intervals do not correct unrepresentative sampling.
8. Pre-register gate thresholds before looking at held-out results. Never treat a perfect small synthetic suite or stable model as proof of reliability.

Do not copy hashes between incompatible schemas to reuse labels. Store private artifacts and credentials outside source control; the offline page contains the supplied cases and must be shared accordingly.
