# Reference evaluation v1 — executable local lane

This additive lane implements the 2026-11-01 recorded-reference study spec.
It does not change production ingestion, V9 targets, old splits or frozen results.
The target is binary END after K=3 preceding positive recorded-hour states,
with train-only entity thresholds, causal predictors and four time partitions.

## Run from the repository root

Use the delivered INSTALL_LOCAL.py and RUN_LOCAL.py for installation/dependency
setup and logged local launching. Individual commands also work:

```powershell
python -m Backend.Benchmark.reference_evaluation.main --help
python -m Backend.Benchmark.reference_evaluation.main audit --download --resume
python -m Backend.Benchmark.reference_evaluation.main validate --resume
python -m Backend.Benchmark.reference_evaluation.main smoke --resume
python -m Backend.Benchmark.reference_evaluation.main all --resume
python -m Backend.Benchmark.reference_evaluation.main export --resume
```

Default config: configs/recorded_hourly_v1.json. Output:
Backend/Output_data/reference_evaluation. Installer places legacy fixture inputs
under that ignored output root. If using another fixture location, pass
--fixture-dir to validate/all. No Firebase credentials, GPU, PyArrow or pytest
are required. Raw official-source network access is enabled only by audit
--download. Offline archives can be declared in runtime.local_archives before
the first study run. A changed config requires a new --output-root.

## Implemented boundaries

- sources.py loads only the official PRSA member pattern and the Appliances
  RH_1 schema. Hour-mean reference requires six distinct finite 10-minute slots;
  partial bins remain unknown with raw dependencies and bin provenance.
- preparation.py creates one shared four-way unique-time split across sites,
  train-only q75 rules, finite-reference segments and a 24-origin warmup.
  CSV canonical/split/support tables use an explicit csv_npz_v1 schema.
- fitting.py fits COMPLETE/SOFT_EM HGB, causal Markov, constant, logistic H6,
  and COMPLETE HGB H24. Four supervised fits per source/train-mask seed, three
  of them HGB. All settings are fixed. A single-class required fit fails support.
- features.py and markov.causal_forecast read past permitted observations only.
  Markov offline marginals belong to the evaluator, not the causal predictor.
- EvaluationSegment contains observed states, keys, fixed scores and score
  mask; no full truth, hidden numeric values, MNAR propensities or corruptions.
  evaluation.py implements paired Brier, point estimates and R0 outer/joint
  bounds. audit.py joins truth only after selection decisions are fixed.
- bounds.py is standard finite-state min/max inference. Its global count budget
  is shared across all eligible segments/sites in one source/partition pool.
  Generic solver uses the identical set and retains primal/dual/status separately.
- sensitivity.py keeps scores fixed across error budgets and explicit synthetic
  archive-reference corruption. These are not hardware-calibration claims.
- reporting.py distinguishes execution completion, support, three-way verdicts,
  action/fallback and later-assessment outcomes. Full plan completion requires
  P2, smoke and all planned cases/solves; no publication/novelty claim is made.

## Correctness and local-only fits

`validate --unit-only` runs focused unit and synthetic integration checks with
HGB/logistic fitting forbidden. It is useful for CI, but does not pass the full
P2 gate. Full `validate` also copies and runs the delivered legacy sensitivity
and generic MILP checks without refitting historical models. The expected
certificate counts at R0..3 are 5/4/1/0; timeout counts may vary by machine.

`smoke` performs four actual supervised toy fits on synthetic train/development
only and checks early real train/development input prefixes. It is an I/O and
implementation gate, never efficacy evidence. Real-source fitting requires full
P2 and completed local smoke. The implementation delivery has not run those
toy fits or any new-source fit on behalf of the user; the user runs them locally.

## Resume and evidence

Every unit records code (including imported package parents), config, inputs,
environment, exact command, logs, metrics and relative artifacts. CLI exit codes
are in invocations/*.json; command.json in a unit records unit_return_code and
links to that receipt. READY.json is written last with file checksums.

Use one CLI process at a time. --resume verifies completed artifact checksums,
reuses matching units and keeps interrupted attempts in separate directories.
Changed inputs or failed replacement audits invalidate current descendant
pointers, without deleting old evidence. ACTIVE_GRAPH.json is the authoritative
current dependency graph, while RUN_INDEX.csv includes old and failed attempts.
Changing numerical environment/code excludes old graph nodes from current use.

`export` creates a local drive_sync tree with readable indexes and new immutable
artifacts, plus public raw-release provenance (not repeated raw archives).
Only files declared in READY are copied from units. It never reports a Drive
upload or synthesizes remote URLs. Sync drive_sync to the user-owned results
folder, preserve relative paths and add actual upload receipts. Export after the
main command exits to include its completed invocation receipt.

## Scientific scope

Bounds are conditional on the declared feasible-reference set and fixed scores.
INCONCLUSIVE may mean a known tie within tolerance or an uncertain comparison;
the `reason` column distinguishes them. More labels need not resolve a true tie.
They are not population confidence intervals, a future-ranking guarantee or
physical event validation. The selected primary pool excludes genuinely missing
reference gaps; coverage/exclusions remain in the audit. Mask seeds, sites and
training masks do not become independent datasets. A dominant fixed candidate
must be reported, not removed to create selector difficulty.

The new lane generalizes the delivered Jena inference reference; it does not
claim the DP, paired bounds, error-count state or three-way decision is novel.
Inspect support and fixed baselines before extending the research claim.
