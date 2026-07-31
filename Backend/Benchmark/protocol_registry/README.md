# Protocol Registry

`protocol_registry` is the upstream authority for environment facts,
stage-dependent visibility, fold/cohort policy, future-target activation, and
experiment-arm permissions.

It reads only a versioned protocol configuration and the Layer1 manifest. It
does not import weak-label, dataset-view, evaluation, validity, or model code.

## Phase A contract

- E1 is fully visible for discovery diagnostics.
- E2 and `E3_TARGET_PREEXPOSED` are structural-only.
- E3 is a previously exposed target; its registered role is protocol-locked
  transport re-evaluation, not untouched evaluation.
- `E4_FUTURE_TARGET` is a non-materialized policy until a real Phase B freeze
  timestamp and post-freeze records exist.
- `E1_PRIMARY_7D_V1` is primary; `E1_DIAGNOSTIC_5D_V1` is diagnostic.
- `E1_DISCOVERY_TRAIN_V1` is an independent 21-day threshold-fit cohort.

Environment facts never contain permissions. The visibility registry is the
stage authority, and an experiment arm may only narrow those permissions.

## Command

```powershell
python Backend\Benchmark\protocol_registry\main.py
```

The command writes a versioned run under `protocol_registry/artifacts/`.
Downstream governed consumers must receive that run directory explicitly.

## Public API

```python
build_protocol_registry(config_path, canonical_manifest_path) -> Path
load_protocol_registry(run_dir) -> ProtocolRegistry
authorize_operation(registry, stage_id, environment_id, operation) -> AuthorizationDecision
authorize_arm_operation(registry, stage_id, environment_id, arm_id, operation) -> AuthorizationDecision
```

Phase A registries contain `phase_a_only=true`. Evaluation and validity
consumers fail closed against such a registry and cannot pass the STOP gate.
They also contain `downstream_runners_unlocked=false`, so changing only the
stage flag cannot bypass the pending 7-day-primary runner migration.

## Phase B frozen registry

Phase B creates an additive `CONTRACT_FROZEN` registry linked to a reviewed
semantic-contract run. Such a registry has:

- `phase_a_only=false`;
- `semantic_contract_frozen=true`;
- `native_engine_implemented=false`;
- `downstream_runners_unlocked=false`.

The frozen registry records the semantic-contract hash, review decision hash,
freeze timestamp, and canonical record-set commitment. It does not unlock
evaluation or validity runners and does not materialize labels. E3 remains a
pre-exposed protocol-locked re-evaluation target; E4 remains a policy until
post-freeze governed snapshots provide eligible records.

## Phase C native-engine registry

After a successful same-filesystem native-engine publication and verified
success marker, an additive child registry may transition to
`NATIVE_ENGINE_IMPLEMENTED`. It retains `semantic_contract_frozen=true`, sets
`native_engine_implemented=true`, and keeps
`benchmark_release_published=false` and `downstream_runners_unlocked=false`.
A child registry cannot be created from a staging directory or a failed native
run.
