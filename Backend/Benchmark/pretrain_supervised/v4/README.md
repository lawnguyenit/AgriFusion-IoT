# V4

## Purpose

- Downstream benchmark for the full `single_window_features` export.
- Use `single_window_exp6` as the full window set after the single-window ablation suite in `v2`.

## Input

- Pretrain artifact from `single_window_exp6`.

## Output

- `D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\v4\outputs\<DD-MM-YYYY>\<run_name>\`

## Command

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\v4\main.py
```

## Assumptions

- `v4` is the upper-bound benchmark for the current single-window feature family.
- The downstream stack keeps `torch_probe` as the fixed DL head, while the default sklearn suite is compact: `linear_probe` + `xgboost`.
- Extra sklearn heads can be re-enabled with `--model-names`.

## Current Limits

- `v3` handles the multi-window combo benchmark; `v4` stays as the full-set upper bound.
