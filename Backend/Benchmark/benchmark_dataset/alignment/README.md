# Benchmark Input Alignment

## Purpose

`alignment/` reads local Layer1 histories from `Backend/Output_data/Layer1` and aligns them into one benchmark-ready CSV.

This stage does not create labels, real-event audit fields, or downstream engineered features.

## Input

- `D:\AgriFusion-IoT\Backend\Output_data\Layer1`

## Output

- `D:\AgriFusion-IoT\Backend\Benchmark\benchmark_dataset\dataset\benchmark_input_aligned.csv`
- `D:\AgriFusion-IoT\Backend\Benchmark\benchmark_dataset\dataset\manifest.json`

## Schema

- `timestamp`
- `soil_temp`
- `soil_humidity`
- `air_temp`
- `air_humidity`
- `EC`
- `pH`
- `N`
- `P`
- `K`

## Commands

Run only alignment:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\benchmark_dataset\alignment\main.py
```

Run the root dataset pipeline:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\benchmark_dataset\main.py
```

## Assumptions

- `timestamp` is the join key used to align family records.
- `latest/` and `history/` may overlap, so this stage deduplicates by timestamp.
- The output CSV is the benchmark dataset base consumed by `single_window_features` and `multi_window_features`.

## Risks / Limits

- If source histories change schema, this stage fails before downstream builders can run.
- `manifest.json` is the alignment build manifest; later stages write their own build reports separately.
