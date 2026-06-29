# Benchmark Workspace

## Purpose

`Backend/Benchmark` is the reproducible benchmark workspace, kept separate from `Backend/Core` and `Backend/Services`.

The active architecture is:

- `benchmark_dataset/`
- `tabular_benchmark/`
- `reporting/`

## Active Families

### `benchmark_dataset/`

- builds the benchmark base tables
- owns `benchmark_input_aligned.csv`
- owns `benchmark_input_labeled.csv`
- exports single-window and multi-window feature datasets

### `tabular_benchmark/`

- active real-only training family
- supports `binary`, `tri_class`, and `four_class`
- always trains the same 3-model suite:
  - `xgboost`
  - `tabnet_classifier`
  - `ft_transformer_classifier`

### `reporting/`

- shared report/chart aggregation namespace for active benchmark artifacts

## Retained / Historical Families

These trees are not the main active train lane, but they are still kept for specific purposes:

- `context_benchmark/`
  - retained because runtime FT diagnosis and some simulator sizing helpers still read its artifacts
- `pretrain_supervised/`
  - retained for embedding-oriented experiments and historical comparisons
- `tabpfn_benchmark/`
  - retained as an auxiliary benchmark family
- `ft_transformer_benchmark/`
  - retained as a standalone historical family outside the unified `tabular_benchmark` train lane

Historical outputs are kept on disk. Active rebuilds should prefer `benchmark_dataset/` and `tabular_benchmark/` unless a runtime or research consumer explicitly needs one of the retained families.

## Data Flow

1. `benchmark_dataset`
   - rebuilds the benchmark tables and `big_label`
2. `tabular_benchmark/prepare.py`
   - builds a real-only dataset for one label lane
3. `tabular_benchmark/train.py`
   - trains the unified 3-model suite
4. `tabular_benchmark/report.py`
   - generates metric summaries and charts

## Output Layout

Active `tabular_benchmark` artifacts are standardized under:

- `tabular_benchmark/artifacts/binary/datasets/...`
- `tabular_benchmark/artifacts/binary/training/...`
- `tabular_benchmark/artifacts/binary/reports/...`
- `tabular_benchmark/artifacts/tri_class/...`
- `tabular_benchmark/artifacts/four_class/...`

## Risks / Limits

- `tri_class` and `four_class` remain highly imbalanced on real-only data
- historical outputs still exist on disk, and some older tooling may still need fallback handling for them
