# Benchmark Common

## Purpose

This module holds benchmark-wide path registries shared by the active
forward benchmark families.

It exists to prevent each benchmark package from rebuilding `Path(__file__).resolve().parents[...]`
with slightly different assumptions.

## Input

- `Backend.Config.paths.BACKEND_PATHS`

## Output

- Shared constants such as:
  - `BENCHMARK_ROOT`
  - `DATASET_VIEWS_ROOT`
  - `WEAK_LABELS_ROOT`
  - `EVALUATION_PROTOCOLS_ROOT`
  - `VALIDITY_LIFECYCLE_ROOT`
  - `MODEL_SUITE_ROOT`

## Command

This module is import-only and has no standalone command.

## Assumptions

- `Backend/Config/paths.py` remains the single source of truth for backend-level directories.
- The active benchmark authority lanes continue to live under
  `Backend/Benchmark/`.

## Risks / Limits

- This module standardizes active benchmark roots only.
- Direct-execution entrypoints may still keep a small `sys.path` bootstrap block so they can run as scripts.
