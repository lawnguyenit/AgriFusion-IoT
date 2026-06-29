# Multi-Window Benchmark Exports

## Purpose

`multi_window_features/` builds multi-window benchmark exports on top of the labeled benchmark dataset.

These exports are used by:

- `pretrain_supervised/v3`
- `tabular_benchmark` raw control arm `v3`

This stage is separate from `single_window_features` so combo experiments stay distinct from the single-window family.

## Input

- `D:\AgriFusion-IoT\Backend\Benchmark\benchmark_dataset\dataset\benchmark_input_labeled.csv`

## Output

- `D:\AgriFusion-IoT\Backend\Benchmark\benchmark_dataset\dataset\multi_window_combo1.csv`
- `D:\AgriFusion-IoT\Backend\Benchmark\benchmark_dataset\dataset\multi_window_combo2.csv`
- `D:\AgriFusion-IoT\Backend\Benchmark\benchmark_dataset\dataset\multi_window_combo3.csv`
- `D:\AgriFusion-IoT\Backend\Benchmark\benchmark_dataset\dataset\multi_window_combo4.csv`
- `D:\AgriFusion-IoT\Backend\Benchmark\benchmark_dataset\dataset\multi_window_feature_build_report.json`

## Combo Meaning

- `combo1`
  - base columns + 3h and 8h windows
- `combo2`
  - `combo1` + one-step deltas
- `combo3`
  - base columns + 3h, 8h, and 24h windows
- `combo4`
  - `combo3` + one-step deltas

## Commands

Build all combos:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\benchmark_dataset\multi_window_features\main.py
```

Build one combo:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\benchmark_dataset\multi_window_features\main.py --experiment combo2
```

Build combos through the root pipeline:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\benchmark_dataset\main.py --skip-single-window-features
```

## Assumptions

- Combo exports reuse the same labeled benchmark base as single-window features.
- This stage changes feature composition only; it does not generate labels.
- Train-facing exports keep `big_label` only when the source CSV already carries labels.
- The build report records the selected combos and generated files.

## Risks / Limits

- Combo exports still depend on enough lookback history for longer windows.
- This stage does not create or validate the real labeled CSV.
