# Pretrain

## Purpose

- Create self-supervised embeddings from benchmark CSVs produced by fuzzy layers.
- Learn representations with masked feature reconstruction before downstream supervised training.

## Input

- `v1 / layer1`
  - `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_input_aligned.csv`
- `v0 / layer0`
  - `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_input_aligned.csv`
  - `layer0_ph`
  - `layer0_npk`
  - `layer0_ph_npk`
- `v2 / layer2`
  - `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_l2_exp1.csv`
  - `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_l2_exp2.csv`
  - `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_l2_exp3.csv`
  - `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_l2_exp4.csv`
  - `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_l2_exp5.csv`
  - `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_l2_exp6.csv`
- `v3 / layer3_combo`
  - `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_l3_combo1.csv`
  - `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_l3_combo2.csv`
  - `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_l3_combo3.csv`
  - `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_l3_combo4.csv`
- `v4`
  - full-set benchmark that consumes `layer2_exp6`

## Output

- `D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\pretrain\outputs\<DD-MM-YYYY>\<run_name>\`

The JSON/YAML reports still keep the full `run_id` with timestamp. The folder name is shortened because the date is already encoded in the parent bucket.

Main artifacts:
- `cleaned_input.csv`
- `feature_schema.json`
- `scaler.pkl`
- `scaler_stats.json`
- `split_manifest.json`
- `split_train.csv`
- `split_validation.csv`
- `split_test.csv`
- `split_excluded_gap.csv`
- `pretrain_config.yaml`
- `pretrain_report.json`
- `pretrain_checkpoint.pt`
- `validation_reconstruction_loss.json`
- `training_metrics.csv`
- `monitoring_summary.json`
- `run_status.json`

## Command

Train Layer 1 baseline:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\pretrain\main.py --benchmark-version v1
```

Train Layer 0 nutrient/pH ablations:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\pretrain\main.py --benchmark-version v0 --source-kind layer0_ph
python D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\pretrain\main.py --benchmark-version v0 --source-kind layer0_npk
python D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\pretrain\main.py --benchmark-version v0 --source-kind layer0_ph_npk
```

Train the full Layer 2 ablation schema:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\pretrain\main.py --benchmark-version v4
```

Train a specific Layer 2 ablation:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\pretrain\main.py --benchmark-version v2 --source-kind layer2_exp3
```

Train a Layer 3 combo benchmark:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\pretrain\main.py --benchmark-version v3 --source-kind layer3_combo2
```

Train with stricter early stopping:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\pretrain\main.py --benchmark-version v2 --source-kind layer2_exp4 --max-epochs 120 --patience 12 --early-stopping-min-delta 0.001
```

Export embeddings:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\pretrain\infer.py --checkpoint D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\pretrain\outputs\<DD-MM-YYYY>\<run_name>\pretrain_checkpoint.pt --output-csv D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\pretrain\outputs\<DD-MM-YYYY>\<run_name>\embeddings.csv --mode embedding
```

## Assumptions

- `timestamp` is used only for sorting, time feature creation, and split creation. Raw timestamp is not used directly as a model feature.
- default pretrain budget is `100` epochs unless `--max-epochs` is passed explicitly
- each source schema declares its own required columns and model feature columns
- if annotation columns such as `big_label` or `event_primary` exist in the CSV, pretrain preserves them as non-feature columns so downstream can reuse them later
- early stopping resets only when validation loss improves by more than `early_stopping_min_delta`
- split creation is now owned by:
  - `D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\split_policy`
  - current default strategy is `chronological_with_lookback_gap`
  - if feature columns include windows such as `8h` or `24h`, the split gap is inferred automatically from the maximum lookback horizon unless overridden

## Current Limits

- `v0` is the nutrient/pH ablation contract before the Layer1 baseline
- `v3` is the Layer 3 combo contract for multi-window mixtures
- `v4` is the full-set benchmark contract for `layer2_exp6`
- `chronological_with_lookback_gap` is fairer than the old split, but it still does not implement day-block or episode-aware evaluation
- compatibility alias paths from older commands may still exist elsewhere in the repo, but this folder is the canonical pretrain path
- Layer2 now has six ablation exports, and `layer2_exp6` is the full-set schema used by `v4`
