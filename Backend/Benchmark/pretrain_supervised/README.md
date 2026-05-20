# Pretrain Supervised Benchmark

## Purpose

This folder keeps the full benchmark flow:

- embedding pretrain
- downstream supervised experiments
- versioned schema evolution
- split and label policy documents

## Layout

- `pretrain/`
  - canonical embedding stage
- `reports/`
  - report generators for charts, profile summaries, version summaries, and Word packs
- `maintenance/`
  - housekeeping scripts for reorganizing outputs
- `notes/`
  - small scratch metadata such as the model list catalog
- `outputs/`
  - date-bucketed run folders under each version output root
- `split_policy/`
  - reusable split strategy module and split ownership
- `v1/`
  - downstream for embeddings generated from `layer1`
- `v2/`
  - downstream for embeddings generated from `layer2_exp1..exp5`
- `v3/`
  - downstream for embeddings generated from `layer3_combo1..layer3_combo4`
- `v4/`
  - downstream for the Layer2 full-set export `layer2_exp6`
- `direct_benchmark/`
  - sibling control-arm benchmark on raw `v0/v1` features without embedding pretraining
- `reports/generate_charts.py`
  - render PNG charts from pretrain or downstream run folders
- `reports/generate_version_summary.py`
  - build a version-level summary across `v0` to `v4` and render aggregate comparison charts
- `reports/generate_report_pack.py`
  - build a Word-friendly decision pack with selected pretrain candidates, downstream roles, and per-version/per-experiment comparison charts
- `reports/generate_data_profile_report.py`
  - build a dataset profile report for raw Firebase counts, cleaned/train-ready rows, and pre-collapse abnormal label distributions
- `charts_summary/`
  - version-level summary exports grouped by date
- `report_pack/`
  - candidate-selection exports and Word-friendly charts grouped by date
- `report_pack_lite/`
  - compact Word-friendly packs with fewer charts and 2-decimal annotations grouped by date
- `data_profile_report/`
  - dataset size and label-scarcity exports grouped by date

## Policy Documents

- `LABEL_POLICY.md`
  - current meaning of `normal`, `abnormal`, `big_label`, and grouped labels
- `SPLIT_POLICY.md`
  - current split strategy and planned stricter split regimes

## Version Contract

- `v1`
  - consume output of `pretrain` when source is `layer1`
- `v2`
  - consume output of `pretrain` when source is `layer2_exp1..layer2_exp5`
  - keep artifacts separated by `run -> experiments -> expN -> models`
- `v3`
  - consume output of `pretrain` when source is `layer3_combo1..layer3_combo4`
- `v4`
  - consume output of `pretrain` when source is `layer2_exp6`

## Assumptions

- each version keeps its own schema contract
- if the input schema changes strongly, the matching pretrain and downstream version must also change
- downstream versions consume embeddings or pretrain artifacts, not raw fuzzy-layer CSVs directly
- run folders are date-bucketed as `outputs/DD-MM-YYYY/<run_name>` while the report keeps the full timestamped `run_id`
- Layer2 ablations are now split more cleanly: `exp2=3h`, `exp3=8h`, `exp4=24h`, `exp5=saturation`
- `exp6` is the full-set benchmark and now belongs to `v4`
- `reports/generate_version_summary.py` scans the latest run for each version and produces summary CSV/PNG artifacts under `charts_summary/<YYYY-MM-DD>-summary`
- `reports/generate_version_summary.py` now emits a readable `best_model_panels.png` plus a detailed `model_metrics_heatmap.png` appendix
- `reports/generate_report_pack.py` is the preferred export for report writing: it selects one pretrain candidate per version, marks downstream baseline/contrast/main roles, and renders per-version/per-experiment validation vs test charts
- `reports/generate_report_pack.py --lite` generates a compact Word pack with fewer charts, 2-decimal annotations, and a version-trajectory overview
- `reports/generate_data_profile_report.py` is the preferred export for dataset size and label-scarcity reporting

## Current Limits

- `v3` is the Layer3 combo benchmark for multi-window feature mixtures
- `v4` is the full-set downstream benchmark for `layer2_exp6`
- the current split strategy is still `chronological_v1`, which is reproducible but not yet strict enough for serious leakage control
- some fuzzy-side documentation is still stale and must be aligned with the actual tree
- the version summary chart is aggregate-level only; for per-run drilldown use `reports/generate_charts.py`
