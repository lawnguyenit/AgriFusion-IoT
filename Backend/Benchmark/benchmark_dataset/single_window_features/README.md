# Single-Window Benchmark Exports

## Purpose

`single_window_features/` builds the single-window benchmark feature exports used by:

- `pretrain_supervised/v2`
- `pretrain_supervised/v4`
- `tabular_benchmark` raw control arms `v2`, `v4`, `v5`

This stage consumes `benchmark_input_labeled.csv` by default and writes feature-engineered benchmark CSVs.
If the canonical artifact is not present, it automatically falls back to the active `flb_input_with_events.csv` export in the same dataset folder.
Each export retains `big_label` only, without carrying the full event-audit payload from the real-label source file.

## Input

- `D:\AgriFusion-IoT\Backend\Benchmark\benchmark_dataset\dataset\benchmark_input_labeled.csv`
- fallback active artifact: `D:\AgriFusion-IoT\Backend\Benchmark\benchmark_dataset\dataset\flb_input_with_events.csv`

## Output

- `D:\AgriFusion-IoT\Backend\Benchmark\benchmark_dataset\dataset\single_window_exp1.csv`
- `D:\AgriFusion-IoT\Backend\Benchmark\benchmark_dataset\dataset\single_window_exp2.csv`
- `D:\AgriFusion-IoT\Backend\Benchmark\benchmark_dataset\dataset\single_window_exp3.csv`
- `D:\AgriFusion-IoT\Backend\Benchmark\benchmark_dataset\dataset\single_window_exp4.csv`
- `D:\AgriFusion-IoT\Backend\Benchmark\benchmark_dataset\dataset\single_window_exp5.csv`
- `D:\AgriFusion-IoT\Backend\Benchmark\benchmark_dataset\dataset\single_window_exp6.csv`
- `D:\AgriFusion-IoT\Backend\Benchmark\benchmark_dataset\dataset\single_window_feature_build_report.json`

## Experiment Meaning

- `exp1`
  - base Layer1 columns + one-step deltas
- `exp2`
  - `exp1` + 3h window features
- `exp3`
  - `exp1` + 8h window features
- `exp4`
  - `exp1` + 24h window features
- `exp5`
  - `exp1` + air-humidity saturation persistence features
- `exp6`
  - full single-window feature set

## Commands

Build all single-window exports:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\benchmark_dataset\single_window_features\main.py
```

Build one export:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\benchmark_dataset\single_window_features\main.py --experiment exp3
```

Build single-window exports through the root pipeline:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\benchmark_dataset\main.py --skip-multi-window-features
```

## Assumptions

- All temporal windows are backward-looking.
- Single-window features own this benchmark feature-engineering stage, not label generation.
- Train-facing exports keep `big_label` only when the source CSV already carries labels.
- `exp2` exports only rows whose 1-step delta and 3h window features are fully defined from real history; this stage does not zero-fill missing lookback context.
- The build report records which exports were requested and which files were written.

## Risks / Limits

- `exp2` now drops rows with incomplete 1-step or 3h lookback coverage instead of exporting NaN values into the train-facing CSV.
- Other experiments still follow their current export policy and may require their own validity rules if they are promoted into an official benchmark lane later.
- This stage does not validate or create `benchmark_input_labeled.csv`; it only reuses it when present.
