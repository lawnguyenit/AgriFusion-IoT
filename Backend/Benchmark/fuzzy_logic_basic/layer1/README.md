# Layer1 - FLB Input Alignment

## Purpose

`layer1/` reads local Layer1 histories from `Backend/Output_data/Layer1` and aligns them into one benchmark-ready CSV.

This stage does not create labels, real-event audit fields, or downstream engineered features.

## Input

- `D:\AgriFusion-IoT\Backend\Output_data\Layer1`

## Output

- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_input_aligned.csv`
- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\manifest.json`

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

Run only Layer1:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\layer1\main.py
```

Run the root dataset pipeline:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\main.py
```

## Assumptions

- `timestamp` is the join key used to align family records.
- `latest/` and `history/` may overlap, so this stage deduplicates by timestamp.
- The output CSV is the benchmark dataset base consumed by `layer2` and `layer3_combo`.

## Risks / Limits

- If source histories change schema, this stage fails before downstream builders can run.
- `manifest.json` is the Layer1 build manifest; later stages write their own build reports separately.
