# V0

## Purpose

- Nutrient and pH ablation benchmark before the Layer1 baseline.
- This version compares raw pH, raw NPK, and combined pH+NPK against the same aligned sensor base used by `v1`.

## Input

- Pretrain artifacts from:
  - `layer0_ph`
  - `layer0_npk`
  - `layer0_ph_npk`

## Output

- `D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\v0\outputs\<DD-MM-YYYY>\<run_name>\`

## Command

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\v0\main.py
```

## Assumptions

- `v0` uses the same aligned benchmark CSV as `v1`, but with the nutrient and pH raw fields turned into explicit features.
- The downstream model suite is the same family used by `v1`, `v2`, `v3`, and `v4`.

## Current Limits

- This version is still proxy-label downstream training; it does not turn pH or NPK into direct ground truth.
- It is meant to test whether keeping pH/NPK helps or hurts before the `v1` baseline.

