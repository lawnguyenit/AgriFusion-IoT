# V3

## Purpose

- Downstream benchmark for the Layer3 combo export family.
- This version compares multi-window combinations without the saturation features reserved for `v4`.

## Input

- Pretrain artifacts from:
  - `layer3_combo1`
  - `layer3_combo2`
  - `layer3_combo3`
  - `layer3_combo4`

## Output

- `D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\v3\outputs\<DD-MM-YYYY>\<run_name>\`

## Command

Build the Layer3 combo CSVs:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\layer3_combo\main.py
```

Pretrain the default combo source:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\pretrain\main.py --benchmark-version v3
```

Train downstream models:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\v3\main.py
```

## Assumptions

- `v3` is the benchmark slot for multi-window combo analysis.
- The downstream stack keeps `torch_probe` as the fixed DL head, while the default sklearn suite is compact: `linear_probe` + `xgboost`.
- Extra sklearn heads can be re-enabled with `--model-names`.

## Current Limits

- `v3` focuses on window combinations only; saturation remains outside this family so `v4` can remain the full-set upper bound.
- It still shares the same proxy-label downstream setup used by the other embedding benchmarks.
