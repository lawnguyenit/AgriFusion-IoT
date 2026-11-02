# P2: immutable, no-refit correctness pilot

Additive sibling of reference_evaluation; never modifies its source, configuration,
graph, READY, labels, splits or output units. Requires passed P1 for report
current_graph__71b84c1ff33cc2a3 and the original dedicated Python environment.

From the resolved repository root (do not use a different interpreter):

```powershell
$env:OMP_NUM_THREADS='2'
$env:OPENBLAS_NUM_THREADS='2'
$env:MKL_NUM_THREADS='2'
$env:PYTHONDONTWRITEBYTECODE='1'
& Backend/Output_data/reference_evaluation/_venv/Scripts/python.exe -m unittest Backend.Benchmark.reference_evaluation_p2.tests.test_pilot -v
& Backend/Output_data/reference_evaluation/_venv/Scripts/python.exe -m Backend.Benchmark.reference_evaluation_p2.runner --repo . --output Backend/Output_data/reference_evaluation_p2/pilot_r0_seed11_v1
```

Existing destinations are refused, including incomplete ones: retain failure
evidence and choose a new explicit attempt path. Never delete old units to retry.
No RunStore construction, v1 CLI, dataset download or model fit is used.
Classifier fit methods and fit_candidates are blocked during CLI execution.

P2_LOCK.json declares the scope before work: two sources, K3, training11,
mcar30/block30, selection/assessment, global R0. All eight original shared-mask
cases get min/max witnesses, whether or not their endpoints illustrate ambiguity.
Primary orientation is SOFT_EM_HGB minus COMPLETE_HGB. This pilot does not compute
full-pool G; P1 replay remains the separate full-pool evidence.

A: cached unmasked recorded forecasts with independently masked reference.
B: role-separated feature mask11, cache-generated causal forecasts, full reference.
C: exactly B's forecasts with reference seeds11/22 in a different namespace.
D: existing v1 shared-mask11 forecasts/reference, with byte-verified inputs and
matching original pair endpoints. Fixed train normalization and candidate pool
are reused; no imputation/fitting settings are estimated from either audit period.
Reference-only changes preserve prediction and scored-cohort hashes for all models.

Project joblib caches are loaded only after verifying their READY hashes. Cache
predictions must reproduce frozen full-control hashes before new B/C forecasts.
Numeric hidden values and audit truth never enter primary_bounds/traceback;
EvaluationSegment remains the unchanged public contract. MCAR/block generation
uses the source simulation adapter, not an evaluator truth channel.

Outputs: mask_ablation.csv, witness_index.csv, per-branch public_inputs.npz,
downstream audit_only/truth.npz, full min/max completion NPZs, role/seed records,
provenance, validation, source copy and new P2_READY.json checksums. Independent
validator recomputes END at segment boundaries and original fixed-probability
Brier; saved witness files are reopened and checked. Observations and global R0,
warmup, unique keys, score and cohort must match. Hypothetical witness completions
are derived evidence, never observed measurements.

Tests exhaustively compare toy completions to traceback and old rolling DP,
validate independent seed roles and fixed-p invariance, full-control collapse,
boundary resets, malformed inputs and persisted-witness tamper rejection.

Only opposite attained strict orders justify the float-verified ambiguity label.
Zero endpoints distinguish tie/strict order; numerical uncertainty remains explicit.
There is no exact-arithmetic proof claim, R>0 traceback, new-method claim or future
ranking guarantee. Appliances limited_support persists. P3/P4 are not run.
