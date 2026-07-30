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

### `weak_labels/`

Weak-label authority lane.

Responsibilities:

- consumes canonical telemetry keyed by `record_id`
- builds point and temporal-window label artifacts
- separates evidence and exclusion states from train labels
- versions rule sources, proxy dependencies, and audits

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
2. `dataset_views` materializes feature views from canonical rows.
3. `weak_labels` materializes auditable label artifacts from the same
   canonical source.
4. `evaluation_protocols` combines dataset views and weak labels into
   source/target benchmark assignments and diagnostics.
5. `validity_lifecycle` re-audits the frozen benchmark contract as
   lifecycle-ready evidence before later train or falsification work.

For the implemented end-to-end handoff from benchmark lanes into
`model_suite`, read:

- `Backend/Benchmark/BENCHMARK_TO_MODEL_SUITE_SPEC.md`

## Current Limits

- `v4_hybrid` remains reserved
- V3, V5, and V6 are removed from the active benchmark runtime surface

## Detailed Flow Docs

Read these when you need implemented control flow instead of only lane
boundaries:

- [Dataset Views Flow](dataset_views/FLOW.md)
- [Weak Labels Flow](weak_labels/FLOW.md)
- [Evaluation Protocols Flow](evaluation_protocols/FLOW.md)
- [Validity Lifecycle Flow](validity_lifecycle/FLOW.md)
- [Model Suite Flow](model_suite/FLOW.md)
- [Benchmark to Model Suite Spec](BENCHMARK_TO_MODEL_SUITE_SPEC.md)
