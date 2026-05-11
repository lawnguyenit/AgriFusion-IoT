# TabNet Self-Supervised Pretraining

This folder builds a clean self-supervised TabNet pretraining pipeline for masked feature reconstruction. It does not create event labels and it does not perform supervised fine-tuning.

## Purpose

- Prepare a reproducible pretraining dataset from `flb_input_aligned.csv`.
- Learn a compact representation by masking part of the numerical feature vector and reconstructing only the masked values.
- Save every run to a new timestamped folder for traceability and debugging.

## Input

- Default CSV: `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_input_aligned.csv`
- Default source profile: `layer1`

Expected input columns:

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
- `ec_npk_consistency_score`
- `ec_npk_consistency_flag`

## Source profiles

This benchmark is prepared to accept future fuzzy outputs without changing the model pipeline.

- `layer1`
  Current aligned CSV generated from fuzzy Layer1.
- `layer2`
  Reserved for future fuzzy Layer2 output CSVs.
- `layer3`
  Reserved for future fuzzy Layer3 output CSVs.
- `layer4`
  Reserved for future fuzzy Layer4 output CSVs.
- `layer5`
  Reserved for future fuzzy Layer5 output CSVs.
- `custom`
  Explicit CSV path passed with `--input-csv`.

When a future layer CSV exists, the pipeline can be pointed at it by passing `--source-kind` or `--input-csv` without touching the model code.

## Folder responsibilities

- `main.py`
  CLI entrypoint for pretraining.
- `src/config/`
  Run config, default paths, feature definitions.
- `src/data/`
  Pure data preparation for the model. This stage stops at clean dataframe, chronological split, and scaling inputs.
- `src/model/`
  Pure model code. This stage assumes scaled numerical tensors already exist and only handles architecture, masking, loss, training loop, and checkpointing.
- `src/pipeline/`
  Orchestration layer that connects the data pipeline and the model pipeline without mixing their responsibilities.
- `src/utils/`
  Artifact writing helpers for JSON, YAML, and run folder creation.
- `outputs/pretrain/<run_id>/`
  Immutable per-run artifacts.

## Pipeline boundary

### Data pipeline

Responsible files:

- `src/data/io.py`
- `src/data/cleaning.py`
- `src/data/feature_engineering.py`
- `src/data/splitting.py`
- `src/data/scaling.py`
- `src/pipeline/data_pipeline.py`

Input:

- aligned CSV from `fuzzy_logic_basic`

Output:

- cleaned dataframe
- chronological split metadata
- fitted scaler
- scaled `train / validation / test` arrays
- data artifacts:
  - `cleaned_pretrain_input.csv`
  - `feature_schema.json`
  - `scaler.pkl`

This stage ends before the model is instantiated.

### Model pipeline

Responsible files:

- `src/model/activations.py`
- `src/model/blocks.py`
- `src/model/feature_transformer.py`
- `src/model/attentive_transformer.py`
- `src/model/encoder.py`
- `src/model/decoder.py`
- `src/model/masking.py`
- `src/model/losses.py`
- `src/model/tabnet_pretrainer.py`
- `src/pipeline/model_pipeline.py`

Input:

- scaled feature arrays from the data pipeline

Output:

- trained checkpoint
- validation reconstruction loss history
- per-epoch monitoring CSV and summary JSON

This stage does not read raw CSV directly and does not perform feature engineering.

## Monitoring artifacts

Each run also writes compact monitoring files that are easier to read than charts:

- `training_metrics.csv`
  One row per epoch with train loss, validation loss, best validation loss, learning rate, attention entropy, mask density, grad norm, and epoch duration.
- `monitoring_summary.json`
  Small machine-readable summary for quick status checks or a UI.
- `run_status.json`
  Minimal status file that says whether the run completed and where the key outputs are.

For a beginner, `training_metrics.csv` is the first file to open. It is the simplest way to check whether loss is going down, gradients are stable, and epochs are taking normal time.

## Main feature set

Default model features:

- `soil_temp`
- `soil_humidity`
- `air_temp`
- `air_humidity`
- `EC`
- `pH`
- `hour_sin`
- `hour_cos`
- `dayofweek_sin`
- `dayofweek_cos`
- `gap_minutes_since_prev`

Optional feature when `--include-npk-proxy` is enabled:

- `ec_npk_proxy_index`

`N`, `P`, and `K` are excluded from the main feature set because they are highly correlated with `EC` in this benchmark dataset and should not be treated as independent nutrient measurements.

## Preprocessing assumptions

- Rows are sorted chronologically by `timestamp`.
- `timestamp` is converted into local time features:
  - `hour_sin`
  - `hour_cos`
  - `dayofweek_sin`
  - `dayofweek_cos`
- Raw `timestamp` is kept only for traceability in artifacts and chronological split. It is not used directly as a model feature.
- `gap_minutes_since_prev` is computed from consecutive timestamp differences after sorting.
- Rows with `pH <= 3` are treated as clear artifacts and removed from the clean pretraining dataset.
- Rows where `EC`, `N`, `P`, and `K` are all zero are removed if present.
- `ec_npk_consistency_flag` is used for reporting only. It is not used as a model feature.
- If `include_npk_proxy` is enabled, `ec_npk_proxy_index` is derived from train-split statistics over `EC`, `N`, `P`, and `K` and used as a single proxy feature, not as independent nutrient channels.

## Self-supervised objective

- Randomly mask a fraction of numerical features with `mask_ratio` (default `0.2`).
- Feed the masked vector into a TabNet-style encoder/decoder implemented in plain `torch` blocks.
- Reconstruct only the masked numerical features.
- Optimize masked MSE only on masked elements.

## Split and scaling

- Chronological split only:
  - train: first 70%
  - validation: next 15%
  - test: last 15%
- `StandardScaler` is fit on the train split only.
- The fitted scaler is saved to `outputs/pretrain/<run_id>/scaler.pkl`.

## Run command

Default run:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\tabnet\main.py
```

Explicit source profile:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\tabnet\main.py --source-kind layer1
```

Future fuzzy layer outputs can later be wired the same way once the CSV is generated:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\tabnet\main.py --source-kind layer2 --input-csv D:\path\to\layer2_output.csv
```

Short smoke test:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\tabnet\main.py --smoke-test
```

Optional proxy feature:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\tabnet\main.py --include-npk-proxy
```

## Output

Each run creates a new folder:

- `D:\AgriFusion-IoT\Backend\Benchmark\tabnet\outputs\pretrain\<run_id>\`

Artifacts:

- `cleaned_pretrain_input.csv`
- `feature_schema.json`
- `scaler.pkl`
- `pretrain_config.yaml`
- `pretrain_report.json`
- `tabnet_pretrainer.pt`
- `validation_loss_history.json`
- `training_metrics.csv`
- `monitoring_summary.json`
- `run_status.json`

## Current limitations

- The pretrainer is unsupervised only. It does not fine-tune on event labels.
- The benchmark currently assumes all selected features are numerical.
- The optional EC/N/P/K proxy is exploratory and compresses correlated channels into one feature; it is not a nutrient ground-truth signal.
- `PyYAML` is not required by this implementation. YAML output is written with a lightweight internal serializer because the current environment does not expose the `yaml` module.
- The current TabNet implementation is intentionally explicit for learning and debugging. It favors readability and local control over tight library-level optimization.
