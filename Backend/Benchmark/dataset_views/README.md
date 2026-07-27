# `dataset_views`

`dataset_views` materializes benchmark-facing feature matrices from
frozen Layer1 canonical telemetry. It is the feature authority for the
current benchmark-primary scope and does not attach scientific claims on
its own.

## Current Public Scope

Primary public views:

- `v0_minimal_sensor`
  - full snapshot row view
  - features: `sht.temp_c`, `sht.humidity_pct`,
    `npk.soil_temp_c`, `npk.soil_moisture_pct`, `npk.ec`, `npk.ph`,
    `npk.n_proxy`, `npk.p_proxy`, `npk.k_proxy`
- `v1_sensor_row`
  - reduced snapshot row view
  - features: `sht.temp_c`, `sht.humidity_pct`,
    `npk.soil_temp_c`, `npk.soil_moisture_pct`, `npk.ec`
- `v2_minimal_sensor_window_3h`
  - reduced snapshot `3h` window view
- `v2_sensor_row_window_3h`
  - full snapshot `3h` window view

Optional explicit views:

- `v2_minimal_sensor_window_8h`
- `v2_sensor_row_window_8h`
- `v3_direct`
- `v3_derived`
- `v3_independent`
- `v3_pre_onset`
- `v6_sequence_8h`

Reserved and blocked:

- `v4_hybrid`
- `v5_proxy_reduced`

Alias behavior:

- `v0 -> v0_minimal_sensor`
- `v1 -> v1_sensor_row`
- `v2 -> v2_minimal_sensor_window_3h` and `v2_sensor_row_window_3h`
- `v3 ->` all four V3 subviews
- `v6 -> v6_sequence_8h`

## Inputs

The lane reads:

- `Backend/Output_data/Layer1/canonical/telemetry_history.csv`
- `Backend/Output_data/Layer1/canonical/feature_catalog.csv`
- `Backend/Output_data/Layer1/manifest.json`
- `Backend/Output_data/Layer1/segments/segments_manifest.json` when a
  selected view requires continuity-aware windows or optional V3/V6
  families
- an explicit `--label-artifact` only in `benchmark-ready` mode
- an explicit `--legacy-event-csv` only for the optional V3 family
- an explicit `--legacy-taxonomy-audit-run` only when the user wants a
  historical drift comparison against an older artifact run

It does not read Layer0 raw telemetry and does not mutate Layer1.

## Outputs

Each run creates:

- `Backend/Benchmark/dataset_views/artifacts/<run_id>/`

Run-level guides:

- `ARTIFACT_GUIDE.md`
- `shared/README.md`
- `views/README.md`

Shared artifacts:

- `shared/row_index.*`
- `shared/metadata.*`
- `shared/source_manifest.json`
- `shared/row_index_contract.json`
- `shared/feature_role_registry.csv`
- `shared/feature_dependency_closure.parquet`
- `shared/ablation_view_registry.csv`
- `shared/ablation_subsets/*.json`

Per-view artifacts:

- `views/<view_id>/X.*`
- `views/<view_id>/manifest.json`
- `views/<view_id>/schema.json`
- `views/<view_id>/quality_report.json`
- `views/<view_id>/feature_columns.json`
- `views/<view_id>/feature_lineage.json`

Reports:

- `reports/current_scope_taxonomy_report.json`
- `reports/legacy_taxonomy_drift_audit.json` only when
  `--legacy-taxonomy-audit-run` is provided

## V2 Contract

`v2_*` views are observed-only causal window datasets over frozen
Layer1 rows.

Rules:

- sort and window by `record.ts_sample`
- no synthetic telemetry rows
- no forward-fill, backward-fill, interpolation, or zero sentinels
- continuity resets at segment boundaries, split boundaries, and gaps
  larger than `2.5 * segment_expected_interval_sec`
- `3h` requires at least `6` valid observations and at least `0.75`
  span coverage
- `8h` requires at least `15` valid observations and at least `0.75`
  span coverage
- insufficient evidence remains `NaN`

## Commands

Snapshot group:

```powershell
python Backend\Benchmark\dataset_views\main.py --mode feature-only --views v0 v1
```

Primary temporal group:

```powershell
python Backend\Benchmark\dataset_views\main.py --mode feature-only --views v2
```

Explicit optional `8h` run:

```powershell
python Backend\Benchmark\dataset_views\main.py --mode feature-only --views v2_minimal_sensor_window_8h v2_sensor_row_window_8h
```

Optional V3 family:

```powershell
python Backend\Benchmark\dataset_views\main.py --mode feature-only --views v3 --legacy-event-csv D:\path\legacy_event_labels.csv
```

Optional V6 family:

```powershell
python Backend\Benchmark\dataset_views\main.py --mode feature-only --views v6
```

Explicit historical taxonomy audit:

```powershell
python Backend\Benchmark\dataset_views\main.py --mode feature-only --views v0 v1 --legacy-taxonomy-audit-run D:\path\historical_dataset_views_run
```

Benchmark-ready run:

```powershell
python Backend\Benchmark\dataset_views\main.py --mode benchmark-ready --views v0 v1 --label-artifact D:\path\labels.parquet --label-columns target
```

## Flow

For the short layer contract, see [FLOW.md](FLOW.md).
