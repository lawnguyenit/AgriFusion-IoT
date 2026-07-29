# `dataset_views`

`dataset_views` materializes benchmark-facing feature views directly
from frozen Layer1 canonical telemetry without mutating Layer0 or
Layer1.

As of Wednesday, July 29, 2026, the active runtime surface is limited to
families `v0`, `v1`, and `v2`. Historical `v3`, `v5`, and `v6` family
code has been removed from the active pipeline and is rejected at view
resolution time.

## Active Taxonomy

Public supported views:

- `v0_minimal_sensor`
- `v1_sensor_row`
- `v2_minimal_sensor_window_3h`
- `v2_minimal_sensor_window_8h`
- `v2_sensor_row_window_3h`
- `v2_sensor_row_window_8h`

Compatibility-only non-public view:

- `v2_sensor_window`

Reserved but not implemented:

- `v4_hybrid`

Aliases:

- `v0 -> v0_minimal_sensor`
- `v1 -> v1_sensor_row`
- `v2 ->` all four public V2 subviews

Rejected legacy or removed ids include:

- `v1_full_sensor`
- `v3`
- `v3_direct`
- `v3_derived`
- `v3_independent`
- `v3_pre_onset`
- `v3_metadata_only`
- `v5`
- `v5_proxy_reduced`
- `v5_proxy_reduced_draft`
- `v6`
- `v6_proxy_reduced`
- `v6_event_level`
- `v6a_window_45m`
- `v6a_window_90m`
- `v6a_window_180m`
- `v6b_continuous_sequence`
- `v6c_decoded_episode_registry`

## Current Behavior

- `v0` and `v1` materialize explicit row-wise feature matrices from
  canonical measurement columns.
- `v2` materializes continuity-aware observed-only window features for
  `3h` and `8h`.
- Invalid sensor measurements are masked consistently across row and
  window views.
- `feature-only` mode writes feature artifacts only.
- `benchmark-ready` mode requires an explicit label artifact keyed by
  `record.id`.

There is no active support for operational-lineage (`v3`), proxy
reduction (`v5`), or environmental sequence (`v6`) dataset families.

## Inputs

The active runtime reads:

- `Backend/Output_data/Layer1/canonical/telemetry_history.csv`
- `Backend/Output_data/Layer1/canonical/feature_catalog.csv`
- `Backend/Output_data/Layer1/manifest.json`
- `Backend/Output_data/Layer1/segments/segments_manifest.json`
  for V2 continuity-aware windows

It does not require any legacy weak-label bridge CSV.

## Architecture

Primary modules:

- `main.py`
  - CLI entrypoint
- `pipelines/materialize.py`
  - end-to-end orchestration
- `pipelines/runtime.py`
  - view resolution and runtime validation
- `pipelines/shared_outputs.py`
  - shared row index, metadata, labels, and source manifest
- `pipelines/standard_views.py`
  - dispatch for explicit row views and V2 window views
- `row_views/`
  - explicit row-view materialization for `v0` and `v1`
- `windowing/`
  - continuity-aware V2 feature generation

## Outputs

Each run creates:

- `Backend/Benchmark/dataset_views/artifacts/<run_id>/`

Shared outputs:

- `shared/row_index.parquet`
- `shared/row_index.csv`
- `shared/metadata.parquet`
- `shared/metadata.csv`
- `shared/source_manifest.json`
- `shared/labels.parquet` when labels are attached
- `shared/labels.csv` when labels are attached

Per-view outputs:

- `views/<view_id>/X.parquet`
- `views/<view_id>/X.csv`
- `views/<view_id>/manifest.json`
- `views/<view_id>/schema.json`
- `views/<view_id>/quality_report.json`

Additional V2 outputs:

- `views/<view_id>/window_quality_audit.parquet`
- `views/<view_id>/window_quality_audit.csv`

## Commands

Default supported public views:

```powershell
python Backend\Benchmark\dataset_views\main.py
```

All public V2 subviews:

```powershell
python Backend\Benchmark\dataset_views\main.py --mode feature-only --views v2
```

One V2 subview:

```powershell
python Backend\Benchmark\dataset_views\main.py --mode feature-only --views v2_sensor_row_window_3h
```

Benchmark-ready with explicit labels:

```powershell
python Backend\Benchmark\dataset_views\main.py --mode benchmark-ready --views v0 v1 --label-artifact D:\path\labels.parquet --label-columns target
```
