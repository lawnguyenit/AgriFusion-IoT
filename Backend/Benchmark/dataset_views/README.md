# `dataset_views`

`dataset_views` is the forward row-wise dataset materialization lane for
Benchmark. It reads frozen Layer1 canonical outputs and produces
research-facing dataset variants without mutating Layer0 or Layer1.

## Taxonomy

Authoritative semantic view ids:

- `v0_minimal_sensor`
- `v1_sensor_row`
- `v2_minimal_sensor_window_3h`
- `v2_minimal_sensor_window_8h`
- `v2_sensor_row_window_3h`
- `v2_sensor_row_window_8h`
- `v3_direct`
- `v3_derived`
- `v3_independent`
- `v3_pre_onset`
- `v4_hybrid`
- `v5_proxy_reduced`
- `v6_sequence_8h`

Non-public internal draft:

- `v5_proxy_reduced_draft`

Secondary aliases:

- `v0 -> v0_minimal_sensor`
- `v1 -> v1_sensor_row`
- `v2 ->` all four public V2 subviews
- `v3 ->` all four public V3 subviews
- `v6 -> v6_sequence_8h`

Legacy drifted ids are rejected with targeted errors:

- `v1_full_sensor`
- `v3_metadata_only`
- `v6_proxy_reduced`
- `v6_event_level`
- `v6a_window_45m`
- `v6a_window_90m`
- `v6a_window_180m`
- `v6b_continuous_sequence`
- `v6c_decoded_episode_registry`

## Current Status

Implemented public views:

- `v0_minimal_sensor`
- `v1_sensor_row`
- `v2_minimal_sensor_window_3h`
- `v2_minimal_sensor_window_8h`
- `v2_sensor_row_window_3h`
- `v2_sensor_row_window_8h`
- `v3_direct`
- `v3_derived`
- `v3_independent`
- `v3_pre_onset`
- `v6_sequence_8h`

Current-row explicit measurement views (`v0`, `v1`) mask invalid sensor
measurements by the same sensor-validity rule used by V2, so invalid
NPK/SHT measurements do not remain as misleading numeric values in row
views while becoming missing in window views.

Compatibility-only non-public view:

- `v2_sensor_window`

Reserved but not materialized:

- `v4_hybrid`
- `v5_proxy_reduced`

Internal draft:

- `v5_proxy_reduced_draft`

## Modes

- `feature-only`
  - materializes shared artifacts and requested dataset views
  - does not attach labels unless a view intrinsically carries its own
    benchmark target sidecar such as `v3_pre_onset` or `v6_sequence_8h`
- `benchmark-ready`
  - requires an explicit label artifact keyed by `record.id`
  - fails fast on missing labels or key mismatch

## Inputs

The framework reads only:

- `Backend/Output_data/Layer1/canonical/telemetry_history.csv`
- `Backend/Output_data/Layer1/canonical/feature_catalog.csv`
- `Backend/Output_data/Layer1/manifest.json`
- `Backend/Output_data/Layer1/segments/segments_manifest.json`
  for V2 continuity-aware windows, V3 continuity logic, and V6 cadence
  / continuity handling
- an explicit external `--legacy-event-csv` only when materializing V3
  views that still depend on the deprecated legacy event bridge

It does not read Layer0 raw telemetry.

## Architecture

High-level modules:

- `pipelines/materialize.py`
  - public orchestration entrypoint
- `pipelines/runtime.py`
  - taxonomy resolution, state validation, draft resolution, audit
    discovery
- `pipelines/shared_outputs.py`
  - shared row index, shared metadata, labels, source manifest
- `row_views/`
  - shared explicit row-view framework for `v0`, `v1`, and the internal
    `v5_proxy_reduced_draft`
- `pipelines/standard_views.py`
  - thin dispatch for explicit row views and V2 window views
- `pipelines/v3_family.py`
  - orchestration for V3 operational-lineage shared artifacts and
    subviews
- `pipelines/v6_family.py`
  - orchestration for the single V6 sequence lane plus shared V6
    artifacts
- `windowing/`
  - V2 continuity-aware observed-only window feature generation
- `lineage/`
  - V3 direct, derived, independent, event-registry, and pre-onset
    logic
- `v6_environment/`
  - V6 environment preparation, resampling, target construction,
    chunking, and audit reporting

How to read the tree:

- if a directory name starts matching a semantic family, it owns that
  family's domain logic:
  - `windowing/` => V2
  - `lineage/` => V3
  - `v6_environment/` => V6
- if a directory holds a reusable framework rather than one semantic
  family, it is shared by parameterized views:
  - `row_views/` => explicit row matrices where `v0` and `v1` differ by
    config, not by algorithm
- `pipelines/` should coordinate families, not contain their domain
  rules

## Outputs

Each run creates:

- `Backend/Benchmark/dataset_views/artifacts/<run_id>/`

Shared artifacts:

- `shared/row_index.parquet`
- `shared/row_index.csv`
- `shared/metadata.parquet`
- `shared/metadata.csv`
- `shared/source_manifest.json`
- `shared/labels.parquet` when labels are attached
- `shared/labels.csv` when labels are attached
- `reports/taxonomy_drift_audit.json` when an audited historical
  drifted run is found

Generic per-view artifacts:

- `views/<view_id>/X.parquet`
- `views/<view_id>/X.csv`
- `views/<view_id>/manifest.json`
- `views/<view_id>/schema.json`
- `views/<view_id>/quality_report.json`

Additional V2 artifacts:

- `views/v2_*/window_quality_audit.parquet`
- `views/v2_*/window_quality_audit.csv`

## V2 Contract

`v2_*` views are observed-only causal window datasets built directly
from frozen Layer1 canonical rows.

Core rules:

- sort and window by `record.ts_sample`
- replayed records remain observed samples and are not treated as
  missing after canonical freeze
- no synthetic telemetry rows
- no forward-fill, backward-fill, interpolation, or zero sentinels
- continuity resets at:
  - Layer1 segment boundaries
  - explicit split boundaries
  - continuity gaps larger than `2.5 * segment_expected_interval_sec`
- single invalid packets do not reset continuity

Window evidence policy:

- 3h requires:
  - at least `6` valid observations
  - actual valid-observation span coverage of at least `0.75`
    (`>= 2.25h`)
- 8h requires:
  - at least `15` valid observations
  - actual valid-observation span coverage of at least `0.75`
    (`>= 6h`)
- if a channel fails either requirement, its engineered features remain
  `NaN`
- slope uses the same horizon-evidence gate as the other window
  statistics; it does not emit during warm-up rows that still fail the
  named horizon

Audit behavior:

- `window_quality_audit.*` stays row-aligned with the canonical source
- it includes row identity aliases:
  - `record_id`
  - `timestamp`
  - `continuity_id`
- one-horizon subviews also expose generic audit aliases:
  - `window_horizon_hours`
  - `valid_observation_count`
  - `actual_window_span_sec`
  - `span_coverage_ratio`
  - `max_internal_gap_sec`
  - `window_reset_reason`
  - `eligible_for_training`
- combined compatibility view `v2_sensor_window` keeps horizon-prefixed
  audit fields for both `3h` and `8h`

Additional V3 artifacts:

- `views/v3_*/metadata.parquet`
- `views/v3_*/metadata.csv`
- `views/v3_*/feature_catalog.csv`
- `views/v3_derived/operational_window_audit.parquet`
- `views/v3_derived/operational_window_audit.csv`
- `views/v3_independent/operational_window_audit.parquet`
- `views/v3_independent/operational_window_audit.csv`
- `views/v3_pre_onset/y.parquet`
- `views/v3_pre_onset/y.csv`
- `views/v3_pre_onset/target_audit.parquet`
- `views/v3_pre_onset/target_audit.csv`
- `shared/v3_evidence_ledger.csv`
- `shared/v3_event_registry.parquet`
- `shared/v3_event_registry.csv`
- `reports/v3_generation_report.md`
- `reports/v3_bridge_report.json`

Additional V6 artifacts:

- `V6/sequence_rows.parquet`
- `V6/sequence_rows.csv`
- `V6/chunk_manifest.csv`
- `V6/discarded_chunks.csv`
- `V6/event_fragment_registry.csv`
- `V6/original_event_distribution.csv`
- `V6/day_distribution.csv`
- `V6/chunk_distribution.csv`
- `V6/split_group_manifest.csv`
- `V6/original_event_integrity.json`
- `V6/threshold_manifest.json`
- `V6/X.parquet`
- `V6/X.csv`
- `V6/y.parquet`
- `V6/y.csv`
- `V6/sequence_index.parquet`
- `V6/sequence_index.csv`
- `V6/auxiliary_features.parquet`
- `V6/auxiliary_features.csv`
- `V6/dataset_manifest.json`
- `V6/V6_audit_report.md`
- `views/v6_sequence_8h/manifest.json`
- `views/v6_sequence_8h/schema.json`
- `views/v6_sequence_8h/quality_report.json`

## V6 Contract

`v6_sequence_8h` is a sequence-labeling dataset, not an event-registry
family.

Source and continuity policy:

- source remains frozen Layer1 canonical history
- V6 may create synthetic rows on its own resample grid
- resample cadence is estimated per deployment segment from observed
  sample spacing, with the Layer1 segment manifest as supporting input
- continuity breaks when `delta_time > 180 minutes`
- interpolation is allowed only inside short gaps within a continuity
  segment
- no event or run crosses a continuity break

Chunk policy:

- fixed non-overlapping day chunks:
  - `00:00-08:00`
  - `08:00-16:00`
  - `16:00-24:00`
- chunks are not anchored to continuity-segment starts
- keep chunk only when:
  - `coverage_ratio >= 0.75`
  - the chunk does not contain more than one continuity segment
- discarded chunks remain in audit outputs with explicit
  `discard_reason`

Per-timestep structural channels:

- `sequence.observed_mask`
- `sequence.interpolated_mask`
- `sequence.missing_mask`
- `sequence.time_since_last_observation_sec`

Supervised-loss policy:

- `target_loss_mask` is emitted in `sequence_index`
- by default only observed timesteps participate in supervised loss
- interpolated timesteps remain in `X` but have `target_loss_mask = false`

Primary V6 feature columns:

- `npk.soil_moisture_pct`
- `npk.soil_temp_c`
- `npk.ec`
- `sht.temp_c`
- `sht.humidity_pct`
- `derived.vpd_kpa`
- structural channels listed above

Auxiliary exported-but-not-default columns:

- `npk.ph`
- `npk.n_proxy`
- `npk.p_proxy`
- `npk.k_proxy`

Train labels:

- `normal`
- `persistent_low_relative_moisture_event`
- `unknown_environment_event`

Detailed label and fragment metadata are preserved in `sequence_index`
and `event_fragment_registry`, including:

- `target_loss_mask`
- `online_stage`
- `detailed_event_type`
- `event_id`
- `original_event_id`
- `split_group_id`
- `split_group_kind`
- `event_start_time`
- `event_confirmation_time`
- `event_end_time`
- `fragment_at_chunk_start`
- `fragment_at_chunk_end`
- `crosses_chunk_boundary`

Current V6 intentionally allows cross-chunk event fragmentation. It
records the fragments but does not stitch them back together yet.

Split-group policy:

- event-bearing rows use `split_group_id = original_event_id`
- non-event rows use a chunk-local fallback group
- this keeps later split construction from leaking the same original
  event across train and evaluation partitions

## Commands

Default public views:

```powershell
python Backend\Benchmark\dataset_views\main.py --mode feature-only --views v0 v1
```

V2 family:

```powershell
python Backend\Benchmark\dataset_views\main.py --mode feature-only --views v2
```

One V2 subview:

```powershell
python Backend\Benchmark\dataset_views\main.py --mode feature-only --views v2_sensor_row_window_3h
```

V3 family:

```powershell
python Backend\Benchmark\dataset_views\main.py --mode feature-only --views v3 --legacy-event-csv D:\path\legacy_event_labels.csv
```

V6 sequence lane:

```powershell
python Backend\Benchmark\dataset_views\main.py --mode feature-only --views v6
```

Benchmark-ready with explicit labels:

```powershell
python Backend\Benchmark\dataset_views\main.py --mode benchmark-ready --views v0 v1 --label-artifact D:\path\labels.parquet --label-columns target
```
