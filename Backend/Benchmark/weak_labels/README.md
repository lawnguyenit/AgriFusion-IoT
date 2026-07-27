# Weak Labels

`Backend/Benchmark/weak_labels` is the weak-label authority lane for
benchmark dataset construction from canonical telemetry.

Its responsibilities are:

- build versioned V0/V1 point weak labels;
- build V2 same-Y and temporal weak labels;
- build V6-E event labels and V6-B8 block labels;
- preserve evidence and exclusion states separately from train labels;
- preserve intrinsic applicability and intrinsic exclusion state;
- emit auditable label artifacts without owning protocol split/fold
  authority.

It must not own:

- train / validation / test partitions;
- fold ids;
- deployment-domain roles such as `P1_SOURCE` / `P2_TARGET`;
- purge logic or boundary exclusion created by an evaluation protocol.

For V2 specifically, intrinsic weak-label eligibility covers window
history sufficiency and point-label state only. Horizon-specific purge
for fold boundaries is owned by `evaluation_protocols`, not by
`weak_labels`.

Artifact runs now use a grouped folder contract rather than placing all
files at the run root.

Current artifact layout:

- `run_metadata/`
  - run manifest and artifact catalog
- `registries/`
  - label ontology and dependency registry
- `point/`
  - point evidence, detailed labels, train labels, technical audit
- `v2/`
  - same-Y labels, temporal evidence, temporal labels, matched cohorts,
    and 3h/8h agreement audit
- `v6/`
  - event labels, block composition, block labels, boundary-event audit
- `audits/`
  - label distributions, overlaps, exclusions, example rows
- `threshold_diagnostics/`
  - threshold sensitivity diagnostics

Use `run_metadata/artifact_catalog.csv` as the single entrypoint for
outside readers who need to understand which file is authoritative for
which purpose.

For downstream training, `weak_labels` is only the label-state source.
Runner-facing split/fold authority lives under
`Backend/Benchmark/evaluation_protocols/.../primary_protocol/runner/`,
especially:

- `task_view_registry.csv`
- `task_training_manifest.parquet`

## Detailed Flow

For the implemented orchestration, artifact-writing order, and module
read order, see [FLOW.md](FLOW.md).
