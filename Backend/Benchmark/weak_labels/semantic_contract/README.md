# Phase B Semantic Contract

This lane converts a PASS Phase A readiness run into a reviewed semantic
contract. It is independent from the weak-label engine and never materializes
benchmark labels.

## Phase B1

Run the E1-only decision pack:

```powershell
python Backend\Benchmark\weak_labels\semantic_contract\main.py `
  --phase-a-run-dir Backend\Benchmark\weak_labels\readiness\artifacts\phase_a_readiness_20260731_003845 `
  --protocol-registry-run-dir Backend\Benchmark\protocol_registry\artifacts\protocol_registry_20260731_003841 `
  --canonical-history Backend\Output_data\Layer1\canonical\telemetry_history.csv `
  --output-root Backend\Benchmark\weak_labels\semantic_contract\artifacts
```

The result stops at `PRIMARY_K_REVIEW_REQUIRED`. It contains point contract
replay, an 81-state compatibility matrix, threshold tie diagnostics, and a
Q/K event-geometry scan. K15/K21/K28 from legacy audits are not authority
under the current E1/strict-continuity contract.

## Phase B2

`freeze_semantic_contract` requires a reviewed decision file whose
`reviewed_decision_pack_hash` matches the Phase B1 manifest. It writes an
additive frozen contract and a `CONTRACT_FROZEN` protocol registry. The frozen
registry keeps `native_engine_implemented=false` and
`downstream_runners_unlocked=false` until later phases.

`point_context_incomplete` is outside primary training. Temporal classes are
anchor-conditioned; windows are evidence domains rather than labeled events.
