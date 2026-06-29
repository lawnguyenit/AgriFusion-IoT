# Benchmark Dataset

## Purpose

`benchmark_dataset/` is the active family for benchmark dataset preparation.

It is responsible for:

- aligning Layer1 histories into one benchmark-ready table
- rebuilding `benchmark_input_labeled.csv` from Layer0 metadata
- exporting single-window feature datasets
- exporting multi-window feature datasets

It is not the downstream training family.

## Input

- `D:\AgriFusion-IoT\Backend\Output_data\Layer1`
- Layer0 Firebase metadata used by `real_labeling`

## Output

- `D:\AgriFusion-IoT\Backend\Benchmark\benchmark_dataset\dataset\benchmark_input_aligned.csv`
- `D:\AgriFusion-IoT\Backend\Benchmark\benchmark_dataset\dataset\benchmark_input_labeled.csv`
- `D:\AgriFusion-IoT\Backend\Benchmark\benchmark_dataset\dataset\single_window_exp1.csv` through `single_window_exp6.csv`
- `D:\AgriFusion-IoT\Backend\Benchmark\benchmark_dataset\dataset\multi_window_combo1.csv` through `multi_window_combo4.csv`
- build reports in the same `dataset/` folder

## Commands

Run the full dataset pipeline:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\benchmark_dataset\main.py
```

Run only real labeling:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\benchmark_dataset\real_labeling\main.py
```

Trim active local outputs back to a report cutoff date without touching Layer0 raw data:

```powershell
python D:\AgriFusion-IoT\Backend\main.py --prune-output-after-local-date 2026-05-10
```

## Assumptions

- `benchmark_input_labeled.csv` is the canonical labeled artifact consumed by `tabular_benchmark` and `context_benchmark`
- `big_label` currently carries enough signal to derive `binary`, `tri_class`, and `four_class`
- if the active dataset folder uses `flb_*` artifact names, the benchmark readers and cutoff maintenance command resolve those files as the current working dataset

## Risks / Limits

- real labels are still heuristic, not absolute ground truth
- if the label taxonomy changes deeply, the `big_label` mapping in shared label registries must be updated
