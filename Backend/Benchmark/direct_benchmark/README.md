# Direct Benchmark

## Purpose

This folder is the control-arm benchmark for the AgriFusion-IoT backend.

It exists to answer a simple question:

- if we skip embedding pretraining entirely,
- and train the downstream model suite directly on raw benchmark features,
- how far do we get?

This is the direct counterpart to `pretrain_supervised/`. It is meant for Word-ready comparison and for testing whether pretraining actually adds measurable value.

The direct model suite now includes both ML and DL controls:

- ML: `linear_probe`, `xgboost`
- DL: `tabnet_classifier`

The default suite is intentionally compact so the comparison stays readable. You can expand it with `--model-names` when you need the larger control set, including `torch_probe` and the heavier tree baselines.

## Layout

- `main.py`
  - entrypoint for the direct benchmark run
- `generate_direct_profile_report.py`
  - build a Word-friendly raw-feature profile report with summary table, boxplots, and label composition charts
- `src/`
  - config, raw feature loading, and training pipeline
- `outputs/`
  - date-bucketed run folders with per-experiment metrics and reports

## Versions

- `v0`
  - direct training on the full aligned Layer1 raw sensor + chemistry schema:
    - `soil_temp`
    - `soil_humidity`
    - `air_temp`
    - `air_humidity`
    - `EC`
    - `pH`
    - `N`
    - `P`
    - `K`
- `v1`
  - direct training on the aligned Layer1 environment + EC subset:
    - `soil_temp`
    - `soil_humidity`
    - `air_temp`
    - `air_humidity`
    - `EC`
- `v2`
  - direct training on the Layer2 short-window ablation export `flb_l2_exp2.csv`
- `v3`
  - direct training on the Layer3 combo export `flb_l3_combo2.csv`
- `v4`
  - direct training on the Layer2 full-set export `flb_l2_exp6.csv`
- `v5`
  - union control arm that combines the raw Layer1 schema with the full Layer2 engineered feature set

The direct benchmark does not use any embedding checkpoint.

## Input

- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_input_aligned.csv`
- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_input_with_events.csv`

## Output

Each run writes a new folder under:

- `D:\AgriFusion-IoT\Backend\Benchmark\direct_benchmark\outputs\<DD-MM-YYYY>\<run_name>\`

Main artifacts:

- `direct_dataset.csv`
- `imputer.pkl`
- `scaler.pkl`
- `feature_schema.json`
- `label_policy.json`
- `run_config.json`
- `model_metrics.csv`
- `training_report.json`
- `best_model.txt`
- `run_status.json`
- `tabnet_classifier.pt`
- `torch_probe.pt` when `torch_probe` is enabled

Profile report artifacts:

- `D:\AgriFusion-IoT\Backend\Benchmark\direct_benchmark\data_profile_report\<YYYY-MM-DD>-profile\`
- `*_feature_summary.csv`
- `*_feature_summary_table.png`
- `*_feature_boxplots.png`
- `*_context_timeline.png`
- `*_composition_donut.png`
- `*_profile_report.md`
- `manifest.json`
- `models/`

## Command

Run the full direct benchmark:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\direct_benchmark\main.py
```

Run a smoke test:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\direct_benchmark\main.py --smoke-test
```

Generate the raw-feature profile report for Word:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\direct_benchmark\generate_direct_profile_report.py --experiment v1
```

Run only one experiment:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\direct_benchmark\main.py --experiments v1
```

Run the full matched ladder:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\direct_benchmark\main.py --experiments v0 v1 v2 v3 v4 v5
```

Run the final-report protocol with a fixed 24h purge gap:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\direct_benchmark\main.py --experiments v0 v1 v2 v3 v4 v5 --split-strategy chronological_with_lookback_gap --split-gap-minutes 1440
```

Run the compact model suite explicitly:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\direct_benchmark\main.py --experiments v0 v1 v2 v3 v4 v5 --model-names linear_probe xgboost tabnet_classifier
```

Console progress:

- the pipeline now prints run start, current experiment, model start/finish, and epoch-level progress for `tabnet_classifier`
- sklearn-family models such as `xgboost` now print explicit `fitting` and `completed` messages so long runs are no longer silent
- PyTorch models such as `tabnet_classifier` also print the selected `device` (`cpu` or `cuda`) and CUDA runtime at training start

## Assumptions

- The direct benchmark reuses the current event annotation CSV and the current label policy.
- Splits are built chronologically from the aligned raw rows, using the shared split policy module.
- The downstream model suite is the same family used by the embedding benchmark, so the comparison isolates the effect of pretraining.
- For thesis-grade comparison, the recommended final split is `chronological_with_lookback_gap` with `--split-gap-minutes 1440` so the direct arm and the pretrain arm are evaluated under the same time-based protocol.
- `tabnet_classifier` is the supervised TabNet-style deep model trained directly on raw/control features, not on pretrain embeddings.
- `v1` is intentionally narrower than `v0` so the control arm still contains an explicit raw-feature ablation.
- `v2` to `v5` are the matched direct-feature controls for the temporal/window ladder used in the embedding benchmark.
- Windowed direct experiments can contain missing values in early rows; the downstream pipeline applies median imputation before scaling.
- `torch_probe` is optional and only runs if included in `--model-names`.
- The profile report is a presentation layer only; it does not alter the benchmark data or training flow.

## Limits

- This benchmark is still proxy-label supervised training.
- It does not turn pH/NPK or raw sensor values into ground-truth nutrient diagnosis.
- `v0` and `v1` are control arms, not the final diagnosis target.
- If the raw schema changes strongly, this benchmark should be versioned again instead of being stretched to fit.
