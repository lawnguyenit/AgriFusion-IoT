# `weak_labels`

`weak_labels` is the label-authority lane for Benchmark.

## Package organization

New code uses explicit lifecycle and responsibility namespaces:

```text
weak_labels.contracts
weak_labels.lifecycle.phase_a_readiness
weak_labels.lifecycle.phase_b_contract
weak_labels.lifecycle.phase_c_native
weak_labels.semantic
weak_labels.provenance
weak_labels.infrastructure
```

Historical label source files are no longer part of the executable package.
Only immutable historical artifacts and differential fixtures remain outside
the native implementation. Existing artifact runs and baseline hashes remain
unchanged.

If `dataset_views` prepares `X`, then `weak_labels` prepares `y`.
Both read the same frozen Layer1 canonical evidence, but they own
different contracts:

- `dataset_views` owns feature meaning and feature artifacts
- `weak_labels` owns label meaning, rule traces, and label artifacts

It does **not** own train/validation/test protocol boundaries, fold
purge, environment assignment, or final runner trainability.

## Audit-only Phase A readiness

`weak_labels/lifecycle/phase_a_readiness` is a separate audit path, not an alternate label
engine. It consumes an explicit upstream `protocol_registry` run, audits E1
candidate evidence, writes only structural commitments for E2/E3, and stops
before label materialization or model training.

Its outputs live under:

```text
Backend/Benchmark/weak_labels/artifacts/phase_a/<run_id>/
```

`candidate_resolution/`, `evidence_inventory/`, and
`threshold_diagnostics/` are candidate evidence only and must never be
consumed by the native engine.

Run it explicitly:

```powershell
python Backend\Benchmark\weak_labels\lifecycle\phase_a_readiness\main.py `
  --protocol-registry-run-dir <registry_run_dir> `
  --baseline-weak-label-run-dir Backend\Benchmark\weak_labels\artifacts\weak_labels_20260730_125309 `
  --baseline-weak-label-run-dir Backend\Benchmark\weak_labels\artifacts\weak_labels_20260730_125309_001
```

## Native public tasks

The native release publishes these task families:

- `point`
- `same_y/horizon_3h` and `same_y/horizon_8h` (transfer projections)
- `temporal/horizon_3h` and `temporal/horizon_8h`

`weak_labels` does not consume `dataset_views` outputs. Both lanes read the
same frozen Layer1 canonical source; `evaluation_protocols` later joins the
native labels to feature views and applies fold/purge/train-readiness rules.

## Input

The native lifecycle reads:

- frozen Layer1 canonical history
- Layer1 manifest and canonical evidence schema
- segment manifest and sensor dependency registry
- an explicit frozen Phase B semantic contract

It does not read `dataset_views` outputs directly.

## This Layer Does

`weak_labels` converts canonical evidence into auditable weak targets.

Main responsibilities:

- build point weak labels used by `v0` and `v1`
- build native Same-Y transfer and Temporal labels for `3h` and `8h`
- apply the frozen persistence contract without refitting or exploratory
  overrides during release
- keep technical invalidity separate from environmental label states
- keep intrinsic label eligibility separate from downstream protocol
  exclusions
- emit condition-level rule traces and threshold provenance
- keep tranche-0 assignment provenance explicit by separating:
  - fired semantic rules
  - gate / exclusion outcomes
  - resolution IDs
  - label-transfer lineage

In short:

- `dataset_views` answers: "what features exist for this row/window?"
- `weak_labels` answers: "what weak target state does this row/window
  receive, and why?"

## Output

Each native run is published under the requested output root as:

```text
tasks/point/{assignments,evidence}.parquet
tasks/same_y/horizon_{3h,8h}/assignments.parquet
tasks/temporal/horizon_{3h,8h}/{assignments,evidence}.parquet
cohorts/{intrinsic_eligibility,semantic_fold_projection_manifest}.parquet
audit/{rule_firings,resolutions,assignments,continuity_registry}.parquet
run_metadata/label_release_manifest.json
run_metadata/artifact_catalog.csv
```

Only the Assignment-derived files in `tasks/` are public label authority;
the `audit/` files provide their RuleFiring/Resolution lineage.

Run-level guide:

- `ARTIFACT_GUIDE.md`

For outside readers, the single best entrypoint is:

- `run_metadata/artifact_catalog.csv`

That file tells you which artifact is authoritative for which purpose.

## What Downstream Layers Use

The most important downstream handoff is:

- sample-level weak targets
- assignment / exclusion state
- rule provenance
- threshold provenance

Typical downstream use:

- `evaluation_protocols`
  - combines weak-label authority with feature authority and protocol
    authority
- `model_suite`
  - trains on the protocol-approved subset only
- `validity_lifecycle`
  - reads label dependencies and rule traces during synthesis and
    ambiguity review

## Commands

## Native label release

The contract-gated native engine is the only label-generation lane:

```powershell
python Backend\Benchmark\weak_labels\lifecycle\phase_c_native\main.py --help
```

It requires a complete reviewed Phase B2 contract, reads sensitive evidence
only for authorized E1 records, and writes task-oriented native artifacts.
It publishes Point, Same-Y, and Temporal Assignment artifacts plus a
`run_metadata/label_release_manifest.json`. `evaluation_protocols` consumes
that manifest explicitly. Feature-view admissibility and train-ready
publication remain evaluation responsibilities.

## Flow

For the short layer contract, see [FLOW.md](FLOW.md).
