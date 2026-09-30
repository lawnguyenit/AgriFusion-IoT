# Benchmark Workspace

`Backend/Benchmark` is the research workspace for canonical dataset
construction, weak-label generation, and evaluation protocols. The
current forward architecture keeps dataset materialization, label
authority, and benchmark framing in separate lanes.

## Active Areas

### `dataset_views/`

Canonical feature-view materialization.

Current active scope:

- `v0_minimal_sensor`
- `v1_sensor_row`
- `v2_minimal_sensor_window_3h`
- `v2_minimal_sensor_window_8h`
- `v2_sensor_row_window_3h`
- `v2_sensor_row_window_8h`

Important properties:

- reads frozen Layer1 canonical history and feature governance directly
- writes versioned Parquet artifacts plus CSV debug mirrors
- keeps view taxonomy explicit and auditable
- does not own benchmark fold assignment or model training
- writes both compatibility per-view matrices and a row-identified feature
  superset with value/window group hashes

### `external_intake/`

Source-specific intake for the Stuard tomato irrigation and UCI Air Quality
external datasets. It archives raw releases separately from processed
canonical candidates, records hashes/lineage, and does not create labels or
training features.

### `external_features/`

Uses each intake adapter's measurement allowlist to build a single external
feature superset with observed values and requested causal time windows.
Criterion-only and operational evidence remain in canonical intake data.

### `external_labels/`

Fits external q thresholds on the approved first-21-day calibration window,
maps τ candidates to cadence-specific K, and writes independent target
candidates plus scope-specific support audits. UCI analyzer criteria and
Stuard water-meter readings are not loaded by this lane. It does not select a
primary candidate or create evaluation splits.

### `pretrain_audit/`

Selects available superset feature groups and checks feature/label/split
alignment, feature missingness, and target support before model fitting. It
emits separate selected feature, target, and split artifacts. Current model
training consumers still use their established contracts; the new audit is
available as an explicit gate and is not silently injected into old runs.

### `model_suite/multilabel/`

Additive model lane that consumes a ready pre-train audit, fits independent
binary heads, retains each target's score and metrics, then derives a joint
target-set state. `REF` is produced only for an all-negative prediction; an
unknown truth remains unknown. The existing scalar-label runner is unchanged.

### `weak_labels/`

Weak-label authority lane.

Responsibilities:

- consumes canonical telemetry keyed by `record_id`
- builds point and temporal-window label artifacts
- separates evidence and exclusion states from train labels
- versions rule sources, proxy dependencies, and audits

The audit-only `weak_labels/readiness` sub-lane consumes the upstream
`protocol_registry`, evaluates E1 candidate evidence, structurally seals
E2/E3, and stops before changing labels.

### `protocol_registry/`

Upstream protocol-governance lane.

Responsibilities:

- owns immutable E1/E2/E3 environment facts;
- owns stage visibility and experiment-arm permissions;
- registers 7-day primary and 5-day diagnostic fold policy;
- registers the independent E1 threshold-fit cohort and future E4 activation
  policy;
- authorizes or denies downstream operations without importing later lanes.

### `evaluation_protocols/`

Independent protocol-definition lane.

Responsibilities:

- defines source-development and target-holdout benchmark framing
- emits deployment-domain manifests and rolling temporal folds
- freezes source-fitted threshold policy for transport evaluation
- reports within-position and cross-position diagnostics

Current benchmark-primary scope is intentionally narrower than the full
artifact universe:

- task views: `V0`, `V1`, `V2 same-Y 3h`, `V2 same-Y 8h`
- same-Y comparisons: `V0 vs V2 mini/full` and `V1 vs V2 mini/full`
- final transport evaluation: single-refit `P1 -> P2 target_test`

### `validity_lifecycle/`

Pre-training lifecycle audit lane.

Responsibilities:

- read an authoritative `evaluation_protocols` run;
- map the benchmark sample universe into explicit E1/E2/E3
  environments;
- audit class support, chronological split feasibility, eligibility
  loss, continuity, and matched comparison integrity;
- quantify EC-to-NPK proxy risk and pH stability before later
  lifecycle experiments.

### `model_suite/`

Reusable benchmark model lane.

Responsibilities:

- owns reusable model family definitions
- owns generic tabular preprocessing and model persistence
- serves downstream benchmark consumers such as
  `evaluation_protocols`

### `common/` and `shared/`

Reusable benchmark infrastructure used by the active forward lanes.

## Data Flow

1. Layer1 freezes canonical telemetry and segment metadata.
2. `protocol_registry` freezes environment/protocol authority.
3. `weak_labels/readiness` performs Phase A candidate audits and stops.
4. `dataset_views` materializes feature views from canonical rows.
5. `weak_labels` materializes auditable label artifacts from the same
   canonical source.
6. `evaluation_protocols` combines dataset views and weak labels into
   source/target benchmark assignments and diagnostics.
7. `validity_lifecycle` re-audits the frozen benchmark contract as
   lifecycle-ready evidence before later train or falsification work.
8. Additive external lanes archive/adapt outside datasets, then the new
   pre-train audit can bind an explicit feature selection to target/split
   artifacts before fitting.

For the implemented end-to-end handoff from benchmark lanes into
`model_suite`, read:

- `Backend/Benchmark/BENCHMARK_TO_MODEL_SUITE_SPEC.md`

## Current Limits

- `v4_hybrid` remains reserved
- V3, V5, and V6 are removed from the active benchmark runtime surface
- `source_intake/` is an additive audit/conversion lane; it does not replace
  the immutable existing canonical source without an explicit promotion
  decision.
- `model_suite/analysis/` contains controlled research probes and progression
  runs. Their artifacts are evidence for a question, not automatically the
  primary benchmark release.

## Entry points

Run these from the repository root:

```powershell
python -m Backend.Benchmark.dataset_views.main --help
python -m Backend.Benchmark.external_intake.main --help
python -m Backend.Benchmark.pretrain_audit.main --help
python -m Backend.Benchmark.protocol_registry.main --help
python -m Backend.Benchmark.evaluation_protocols.main --help
python -m Backend.Benchmark.validity_lifecycle.main --help
python -m Backend.Benchmark.model_suite.cli --help
```

The concrete artifact directory is an input to the next lane. A report or
Markdown summary is not a substitute for the machine-readable manifest,
feature matrix, label artifact, split assignment or runner contract that
produced it.

## Detailed Flow Docs

Read these when you need implemented control flow instead of only lane
boundaries:

- [Dataset Views Flow](dataset_views/FLOW.md)
- [Protocol Registry Flow](protocol_registry/FLOW.md)
- [Weak Labels Flow](weak_labels/FLOW.md)
- [Evaluation Protocols Flow](evaluation_protocols/FLOW.md)
- [Validity Lifecycle Flow](validity_lifecycle/FLOW.md)
- [Model Suite Flow](model_suite/FLOW.md)
- [Benchmark to Model Suite Spec](BENCHMARK_TO_MODEL_SUITE_SPEC.md)
