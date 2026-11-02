# Locked mechanism and additional source study

This sibling lane implements the supplied P3–P6 plan without modifying v1/P2.
Numerics reuse v1 compare_pool/pool_bounds and P2 R0 witness reconstruction.
New code owns controlled schedules, explicit calendar folds, Household235 intake,
independent mask roles, HT, full-pool regret reporting and a persistent fit budget.

Protocol authority is protocol.json, copied to PROTOCOL_LOCK.json before metrics.
Unit source inventories, numerical environment, commands, inputs, stdout/stderr,
failure receipts and successful READY checksums are retained. Completed units
are verified on reuse. Failed/interrupted units are never silently marked ready.
Verified model cache registry prevents refitting merely because reporting code
changes. No overwrite of a previous scientific output is allowed.

From the resolved repository root with the original dedicated interpreter:

```powershell
$env:OMP_NUM_THREADS='2'
$env:OPENBLAS_NUM_THREADS='2'
$env:MKL_NUM_THREADS='2'
$env:PYTHONDONTWRITEBYTECODE='1'
& Backend/Output_data/reference_evaluation/_venv/Scripts/python.exe -m unittest Backend.Benchmark.reference_evaluation_next.tests.test_next -v
& Backend/Output_data/reference_evaluation/_venv/Scripts/python.exe -m Backend.Benchmark.reference_evaluation_next.p3 --output Backend/Output_data/reference_evaluation_next/full_20261102_v1
& Backend/Output_data/reference_evaluation/_venv/Scripts/python.exe -m Backend.Benchmark.reference_evaluation_next.p4 --output Backend/Output_data/reference_evaluation_next/full_20261102_v1 --history used_or_unknown
```

P3 runs12 smoke then360 main cases. Six probability schedules are explicitly
synthetic; six canonical model names in input serialization are position aliases,
not claims that HGB/Logistic was fitted. CSV reporting uses SYN names. Forecasts
depend on past states and public generator parameters, never current/future END.
The feasible set uses reference observations; opaque fixed forecast outputs are
not inverted as additional constraints. Every matched high/low block contrast
holds trace/K/p/count/geometry fixed. All ties and reversals are retained.
Discovery/heldout groups and gate are declared in protocol before main.
G uses all15 pairs at R0; R1/3 outputs are primary-pair diagnostics only.
No forecaster fit is permitted during P3.

P4 refuses to run unless P3's frozen gate passes. Source235 is aggregated only
from60 distinct finite valid minute measurements; missing bins stay unknown.
Recorded naive clock is preserved, with no inferred DST or timezone repair.
F1/F2/F3 calendar boundaries, q75 train rule, K3, common24 warmup and all six
candidates are fixed. Segments reset at actual gaps and partition boundaries.
Train input normalization and Markov estimation use permitted training data.
Default model is selected on prescribed development only and frozen.

At most36 supervised fit invocations (27 HGB,9 Logistic if every fit succeeds)
are counted persistently before calls; no HPO, no extra fitting for reference
masks/evaluators.9 fit bundles feed18 forecast bundles and126 reference cells,
each containing selection/assessment. Reference roles never change p/cohort.
Audit truth is written below audit_only, downstream of fixed-score comparison.
Bounds-only pool selection is a separate function without a truth argument.
HT is only computed for independent reference-MCAR; its inclusion probability
counts mutable operands so warmup does not get q^4 incorrectly. It is not clipped.
Block masks do not use HT. Assessment never selects its own operational model.

P4 keeps all support failures and weak folds. Outcome history is user-reported
used/unknown, so this is a locked additional-source extension, not independent
confirmation. Folds, training seeds and masks share source/history and are not
independent datasets. Primary transfer contrast chooses high/low I positions
among the three predeclared block seeds, not by outcome. Future loss comparisons
against every fixed candidate and development default remain separate.

Tests cover exhaustive all-pool G, causal schedules, placement/influence upper
bound, enumerated HT expectation, strict minute aggregation, temporal threshold
and boundary behavior, seed roles and immutable receipts. No actual fits in tests.
P5 is a conditional disposition, never an excuse to add unbudgeted learners.
P6 author-review outputs are separate from private AgriFusion_WADE_V9.
