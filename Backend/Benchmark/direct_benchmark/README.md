# Direct Benchmark

## Purpose

This folder is the control-arm benchmark for the AgriFusion-IoT backend.

It exists to answer a simple question:

- if we skip embedding pretraining entirely,
- and train the downstream model suite directly on raw benchmark features,
- how far do we get?

This is the direct counterpart to `pretrain_supervised/`. It is meant for Word-ready comparison and for testing whether pretraining actually adds measurable value.

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
  - direct training on the pH/NPK raw subset from the aligned Layer1 CSV
- `v1`
  - direct training on the full aligned Layer1 raw schema
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

## Assumptions

- The direct benchmark reuses the current event annotation CSV and the current label policy.
- Splits are built chronologically from the aligned raw rows, using the shared split policy module.
- The downstream model suite is the same family used by the embedding benchmark, so the comparison isolates the effect of pretraining.
- `v0` is intentionally narrower than `v1` so the control arm still contains an explicit raw-feature ablation.
- `v2` to `v5` are the matched direct-feature controls for the temporal/window ladder used in the embedding benchmark.
- Windowed direct experiments can contain missing values in early rows; the downstream pipeline applies median imputation before scaling.
- The profile report is a presentation layer only; it does not alter the benchmark data or training flow.

## Limits

- This benchmark is still proxy-label supervised training.
- It does not turn pH/NPK or raw sensor values into ground-truth nutrient diagnosis.
- `v0` and `v1` are control arms, not the final diagnosis target.
- If the raw schema changes strongly, this benchmark should be versioned again instead of being stretched to fit.
