# Layer3 Combo Benchmark

## Purpose

- Build the multi-window combo benchmark CSVs for the Layer2 family without touching the legacy pressure-focused `layer3` folder.
- This layer is the bridge between the single-window ablations in `layer2` and the full-set upper bound in `v4`.

## Input

- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_input_aligned.csv`

## Output

- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_l3_combo1.csv`
- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_l3_combo2.csv`
- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_l3_combo3.csv`
- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_l3_combo4.csv`

## Command

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\layer3_combo\main.py
```

Specific combo:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\layer3_combo\main.py --experiment combo2
```

## Assumptions

- The combo layer is built from the aligned Layer1 dataset and the shared Layer2 feature builders in `Backend/Core/layer2`.
- All windows are strict backward-looking windows.
- Saturation is intentionally excluded here so `v4` remains the full-set upper bound.

## Current Limits

- This benchmark branch does not encode a new physical label meaning; it only changes the feature combinations used for representation learning.
- The legacy `Backend/Benchmark/fuzzy_logic_basic/layer3` folder is still present and unrelated; do not confuse it with this combo benchmark.

