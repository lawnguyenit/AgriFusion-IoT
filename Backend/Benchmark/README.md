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
- optional legacy-carried V3 views
- `v6_sequence_8h`

Important properties:

- reads frozen Layer1 canonical history and feature governance directly
- writes versioned Parquet artifacts plus CSV debug mirrors
- keeps view taxonomy explicit and auditable
- does not own benchmark fold assignment or model training

### `weak_labels/`

Weak-label authority lane.

Responsibilities:

- consumes canonical telemetry keyed by `record_id`
- builds point, temporal-window, event, and block label artifacts
- separates evidence and exclusion states from train labels
- versions rule sources, proxy dependencies, and audits

### `evaluation_protocols/`

Independent protocol-definition lane.

Responsibilities:

- defines source-development and target-holdout benchmark framing
- emits deployment-domain manifests and rolling temporal folds
- freezes source-fitted threshold policy for transport evaluation
- reports within-position and cross-position diagnostics

### `common/` and `shared/`

Reusable benchmark infrastructure used by the active forward lanes.

## Data Flow

1. Layer1 freezes canonical telemetry and segment metadata.
2. `dataset_views` materializes feature views from canonical rows.
3. `weak_labels` materializes auditable label artifacts from the same
   canonical source.
4. `evaluation_protocols` combines dataset views and weak labels into
   source/target benchmark assignments and diagnostics.

## Current Limits

- `v4_hybrid` and `v5_proxy_reduced` remain reserved
- V3 remains legacy-scoped and now requires an explicit external bridge
  file when requested
- V6 remains more complex than the primary V0-V2 benchmark and should
  be interpreted separately from the core point/window benchmark
