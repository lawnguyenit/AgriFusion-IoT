# Benchmark Common

## Purpose

This module holds benchmark-wide path registries shared by multiple benchmark families.

It exists to prevent each benchmark package from rebuilding `Path(__file__).resolve().parents[...]`
with slightly different assumptions.

## Input

- `Backend.Config.paths.BACKEND_PATHS`

## Output

- Shared constants such as:
  - `BENCHMARK_ROOT`
  - `BENCHMARK_DATASETS_ROOT`
  - `PRETRAIN_ROOT`
  - `TABULAR_BENCHMARK_ROOT`
  - `FT_TRANSFORMER_BENCHMARK_ROOT`
  - `CONTEXT_BENCHMARK_ROOT`
  - `SIMULATOR_ROOT`
- Shared raw-tabular benchmark helpers in:
  - `raw_tabular_dataset.py`
  - source registry for `v0..v5`
  - shared tabular bundle builder reused by `tabular_benchmark`, `ft_transformer_benchmark`, and `tabpfn_benchmark`

## Command

This module is import-only and has no standalone command.

## Assumptions

- `Backend/Config/paths.py` remains the single source of truth for backend-level directories.
- Benchmark families continue to live under `Backend/Benchmark/`.

## Risks / Limits

- This module standardizes roots and shared locations only.
- Direct-execution entrypoints may still keep a small `sys.path` bootstrap block so they can run as scripts.
