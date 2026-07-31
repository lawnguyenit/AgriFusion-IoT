# `weak_labels`

`weak_labels` is the label-authority lane for Benchmark.

If `dataset_views` prepares `X`, then `weak_labels` prepares `y`.
Both read the same frozen Layer1 canonical evidence, but they own
different contracts:

- `dataset_views` owns feature meaning and feature artifacts
- `weak_labels` owns label meaning, rule traces, and label artifacts

It does **not** own train/validation/test protocol boundaries, fold
purge, environment assignment, or final runner trainability.

## Audit-only Phase A readiness

`weak_labels/readiness` is a separate audit path, not an alternate label
engine. It consumes an explicit upstream `protocol_registry` run, audits E1
candidate evidence, writes only structural commitments for E2/E3, and stops
before label materialization or model training.

Its outputs live under:

```text
Backend/Benchmark/weak_labels/readiness/artifacts/<run_id>/
```

`candidate_resolution/`, `evidence_inventory/`, and
`threshold_diagnostics/` are candidate evidence only and must never be
consumed by `build_point_label_artifacts()`.

Run it explicitly:

```powershell
python Backend\Benchmark\weak_labels\readiness\main.py `
  --protocol-registry-run-dir <registry_run_dir> `
  --baseline-weak-label-run-dir Backend\Benchmark\weak_labels\artifacts\weak_labels_20260730_125309 `
  --baseline-weak-label-run-dir Backend\Benchmark\weak_labels\artifacts\weak_labels_20260730_125309_001
```

## Current Scope

Current benchmark-primary weak-label scope:

- `v0_point_train`
- `v1_point_train`
- `v2_same_y_3h`
- `v2_temporal_3h`

Optional explicit outputs still produced by the lane:

- `v2_same_y_8h`
- `v2_temporal_8h`

Important:

- `weak_labels` does not consume `dataset_views` outputs
- both lanes read the same frozen Layer1 canonical source
- `evaluation_protocols` is the later layer that pairs feature views
  with label tasks under a registered protocol contract

## Input

`weak_labels` reads:

- frozen Layer1 canonical history
- frozen Layer1 feature catalog
- Layer1 manifest
- segment manifest for continuity-aware label logic
- weak-label runtime config such as:
  - `base_split_strategy`
  - `run_profile`
  - `threshold_mode`
  - `persistent_low_run_min_steps`

It does not read `dataset_views` outputs directly.

## This Layer Does

`weak_labels` converts canonical evidence into auditable weak targets.

Main responsibilities:

- build point weak labels used by `v0` and `v1`
- build V2 same-Y and temporal weak labels for `3h` and `8h`
- keep the benchmark-default persistence threshold at `k=3` while
  allowing explicit exploratory overrides recorded in the run manifest
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

Each run creates:

- `Backend/Benchmark/weak_labels/artifacts/<run_id>/`

The folder groups are:

- `run_metadata/`
  - run provenance and artifact index
  - key files:
    - `run_manifest.json`
    - `artifact_catalog.csv`
    - `current_scope_summary.json`
- `registries/`
  - label ontology and label-dependency contracts
  - key files:
    - `label_registry.yaml`
    - `label_dependency_registry.csv`
- `point/`
  - point evidence and point weak labels for `v0` / `v1`
  - key files:
    - `point_evidence_flags.parquet`
    - `point_labels_detailed.parquet`
    - `point_labels_train.parquet`
    - `technical_labels_audit.parquet`
- `v2/`
  - V2 same-Y and temporal weak labels
  - key files:
    - `v2_same_y_labels.parquet`
    - `v2_temporal_evidence_3h.parquet`
    - `v2_temporal_labels_3h.parquet`
    - `v2_temporal_evidence_8h.parquet`
    - `v2_temporal_labels_8h.parquet`
    - `matched_cohort_manifest.parquet`
    - `v2_label_agreement_3h_8h.csv`
- `audits/`
  - high-level label summaries and example/exclusion tables
  - key files:
    - `label_distribution.csv`
    - `label_overlap_matrix.csv`
    - `excluded_samples_audit.csv`
    - `label_examples.csv`
- `audit/`
  - tranche-0 scientific trace artifacts
  - key files:
    - `label_assignment.parquet`
      - authoritative assignment provenance including
        `fired_rule_ids`, `primary_fired_rule_id`, `resolution_id`,
        `assignment_mode`, and transfer lineage fields
    - `rule_firings.parquet`
      - condition-level rule and gate evaluation only; same-Y transfer
        does not appear here as a synthetic rule firing
    - `rule_registry.csv`
    - `threshold_registry.csv`
    - `label_source_dependency.csv`
- `threshold_diagnostics/`
  - threshold sensitivity diagnostics
  - key files:
    - `threshold_sensitivity.csv`
    - `persistent_low_k_support.csv`

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

Default run:

```powershell
python Backend\Benchmark\weak_labels\main.py
```

Example with explicit threshold mode:

```powershell
python Backend\Benchmark\weak_labels\main.py --threshold-mode TRAIN_FITTED_GLOBAL
```

Example with exploratory temporal persistence override:

```powershell
python Backend\Benchmark\weak_labels\main.py --persistent-low-run-min-steps 4
```

## Phase C native engine

The contract-gated native engine is a separate additive lane:

```powershell
python Backend\Benchmark\weak_labels\native_engine\main.py --help
```

It requires a complete reviewed Phase B2 contract, reads sensitive evidence
only for authorized E1 records, and writes task-oriented native artifacts.
The legacy command above remains the default and is not modified by a native
run. Feature-view admissibility and train-ready publication are deferred to
Phase D.

## Flow

For the short layer contract, see [FLOW.md](FLOW.md).
