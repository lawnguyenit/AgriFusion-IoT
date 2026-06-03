# Context Classifier Benchmark

## Purpose

This module prepares canonical multi-class benchmark datasets that merge:

- real benchmark rows
- synthetic simulator rows

into one complete context-aware dataset.

It exists to support the benchmark stage that compares:

- `TabNet` as the main tabular model
- `FT-Transformer` as the transformer-style tabular comparator
- `TabPFN` as the pretrained tabular comparator
- `XGBoost` as the tabular control arm
- `LSTM` as the sequence baseline

The module supports parallel label-scheme branches so the original 5-class benchmark and the practical 4-class Option 2 benchmark can coexist without overwriting each other.

## Layout

- `main.py`
  - entrypoint for dataset building
- `train.py`
  - entrypoint for split-aware model training on built datasets
- `report.py`
  - entrypoint for academic comparison reports, tables, and charts across benchmark runs
- `src/config/`
  - runtime configuration and path defaults
- `src/data/canonical_builder.py`
  - normalize real rows and synthetic rows into one canonical schema
- `src/data/splitting.py`
  - split real rows chronologically, then inject synthetic rows into train only
- `src/data/tabular_builder.py`
  - derive tabular `v0/v1/v2/v3` inputs for TabNet, FT-Transformer, TabPFN, and XGBoost
- `src/data/sequence_builder.py`
  - derive a flattened sequence dataset for LSTM
- `src/pipeline/build_pipeline.py`
  - orchestrates the full dataset build
- `src/pipeline/train_pipeline.py`
  - orchestrates the training runs for tabular and sequence models
- `src/model/lstm_classifier.py`
  - in-repo LSTM sequence classifier for the sequence benchmark arm
- `outputs/`
  - original 5-class date-bucketed run folders
- `outputs_option2_4class/`
  - separate date-bucketed run folders for the Option 2 4-class benchmark
- `reports/`
  - generated cross-run charts, CSV summaries, and Markdown reports

## Input

- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_input_with_events.csv`
- latest simulator outputs under `D:\AgriFusion-IoT\Backend\Simulator\outputs\`
  - `synthetic_flb_gap_aware.csv`

## Output

Each run writes a new folder under:

- `D:\AgriFusion-IoT\Backend\Benchmark\context_classifier\outputs\<DD-MM-YYYY>\<run_name>\` for `five_class_v1`
- `D:\AgriFusion-IoT\Backend\Benchmark\context_classifier\outputs_option2_4class\<DD-MM-YYYY>\<run_name>\` for `option2_4class`

Main artifacts:

- `canonical_context_dataset.csv`
- `real_canonical_labeled.csv`
- `synthetic_canonical_labeled.csv`
- `context_label_summary.json`
- `real_label_summary.json`
- `synthetic_label_summary.json`
- `run_config.json`
- `dataset_manifest.json`
- `splits/train/canonical.csv`
- `splits/train/canonical_real.csv`
- `splits/train/canonical_synthetic.csv`
- `splits/train/tabular_v0.csv`
- `splits/train/tabular_v1.csv`
- `splits/train/tabular_v2.csv`
- `splits/train/tabular_v3.csv`
- `splits/train/sequence_long.csv`
- same structure for `validation/` and `test/`

Training artifacts:

- `outputs/training/<DD-MM-YYYY>/context_train_<HHMMSS>/aggregate_model_metrics.csv`
- `outputs/training/<DD-MM-YYYY>/context_train_<HHMMSS>/training_report.json`
- `outputs/training/<DD-MM-YYYY>/context_train_<HHMMSS>/environment_manifest.json`
- `outputs/training/<DD-MM-YYYY>/context_train_<HHMMSS>/scientific_run_manifest.json`
- `outputs/training/<DD-MM-YYYY>/context_train_<HHMMSS>/experiments/v0/...`
- `outputs/training/<DD-MM-YYYY>/context_train_<HHMMSS>/experiments/v1/...`
- `outputs/training/<DD-MM-YYYY>/context_train_<HHMMSS>/experiments/v2/...`
- `outputs/training/<DD-MM-YYYY>/context_train_<HHMMSS>/experiments/v3/...`
- `outputs/training/<DD-MM-YYYY>/context_train_<HHMMSS>/experiments/sequence/...`
- same training structure under `outputs_option2_4class/training/` for `option2_4class`

Per-model scientific artifacts:

- `experiments/<experiment_name>/scientific_artifacts/<model_name>/scientific_manifest.json`
- `experiments/<experiment_name>/scientific_artifacts/<model_name>/training_history.csv`
- `experiments/<experiment_name>/scientific_artifacts/<model_name>/scalar_metrics.csv`
- `experiments/<experiment_name>/scientific_artifacts/<model_name>/classwise_metrics.csv`
- `experiments/<experiment_name>/scientific_artifacts/<model_name>/confusion_matrix.csv`
- `experiments/<experiment_name>/scientific_artifacts/<model_name>/pr_curve_points.csv`
- `experiments/<experiment_name>/scientific_artifacts/<model_name>/roc_curve_points.csv`
- `experiments/<experiment_name>/scientific_artifacts/<model_name>/calibration_curve_points.csv`
- `experiments/<experiment_name>/scientific_artifacts/<model_name>/{train,validation,test}_prediction_records.csv`

Report artifacts:

- `reports/<DD-MM-YYYY>/context_report_<HHMMSS>/combined_model_metrics.csv`
- `reports/<DD-MM-YYYY>/context_report_<HHMMSS>/summary_model_metrics.csv`
- `reports/<DD-MM-YYYY>/context_report_<HHMMSS>/report_summary.md`
- `reports/<DD-MM-YYYY>/context_report_<HHMMSS>/chart_test_macro_f1.png`
- `reports/<DD-MM-YYYY>/context_report_<HHMMSS>/chart_test_accuracy.png`
- `reports/<DD-MM-YYYY>/context_report_<HHMMSS>/chart_test_macro_f1_grouped.png`
- `reports/<DD-MM-YYYY>/context_report_<HHMMSS>/chart_test_accuracy_grouped.png`
- `reports/<DD-MM-YYYY>/context_report_<HHMMSS>/chart_validation_macro_f1_grouped.png`
- `reports/<DD-MM-YYYY>/context_report_<HHMMSS>/chart_test_balanced_accuracy_grouped.png`
- `reports/<DD-MM-YYYY>/context_report_<HHMMSS>/chart_xgboost_feature_ladder.png`
- `reports/<DD-MM-YYYY>/context_report_<HHMMSS>/chart_tabnet_feature_ladder.png`
- `reports/<DD-MM-YYYY>/context_report_<HHMMSS>/chart_label_distribution.png`
- `reports/<DD-MM-YYYY>/context_report_<HHMMSS>/chart_option2_label_mapping.png`
- `reports/<DD-MM-YYYY>/context_report_<HHMMSS>/chart_<label_scheme>_<experiment_name>_<model_name>_curves.png`
  - each learning-curve chart is now isolated to one exact benchmark arm, for example:
  - `chart_five_class_v1_v0_tabnet_classifier_curves.png`
  - `chart_option2_4class_v3_tabnet_classifier_curves.png`
  - `chart_option2_4class_sequence_lstm_classifier_curves.png`

## Command

Build the full dataset package:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\context_classifier\main.py
```

Mac dinh hien tai dung label scheme 4-class canonical `option2_4class`.

Build the Option 2 4-class dataset package:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\context_classifier\main.py --label-scheme option2_4class
```

If the default real labeled artifact does not exist yet, either rebuild it from `fuzzy_logic_basic/real_event_labeling` or pass an explicit real labeled CSV:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\context_classifier\main.py --label-scheme option2_4class --real-event-csv D:\path\to\labeled_real_source.csv
```

Build a smoke-test package:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\context_classifier\main.py --smoke-test
```

Build with explicit simulator inputs:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\context_classifier\main.py --synthetic-gap-aware-csv D:\AgriFusion-IoT\Backend\Simulator\outputs\<run_id>\synthetic_flb_gap_aware.csv
```

Train all context-classifier models from the latest build run:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\context_classifier\train.py
```

Train all Option 2 models from the latest Option 2 build run:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\context_classifier\train.py --label-scheme option2_4class
```

Train only FT-Transformer on the tabular ladder:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\context_classifier\train.py --experiment-names v0 v1 v2 v3 --model-names ft_transformer_classifier
```

Build the latest real+synthetic dataset and immediately train `XGBoost + TabNet + FT-Transformer`:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\context_classifier\train_augmented_tabular.py
```

Reuse an existing build run and retrain the default tabular pipeline:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\context_classifier\train_augmented_tabular.py --build-run-dir D:\AgriFusion-IoT\Backend\Benchmark\context_classifier\outputs_option2_4class\<DD-MM-YYYY>\context_build_<HHMMSS>
```

Build from an explicit simulator run and train `XGBoost + TabNet + FT-Transformer` on `v0/v1/v2/v3`:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\context_classifier\train_augmented_tabular.py --synthetic-gap-aware-csv D:\AgriFusion-IoT\Backend\Simulator\outputs\<run_id>\synthetic_flb_gap_aware.csv
```

Generate a comparison report for the current 5-class and 4-class runs:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\context_classifier\report.py --five-class-run-dir D:\AgriFusion-IoT\Backend\Benchmark\context_classifier\outputs\training\27-05-2026\context_train_095440 --option2-run-dir D:\AgriFusion-IoT\Backend\Benchmark\context_classifier\outputs_option2_4class\training\27-05-2026\context_train_123149 --option2-sequence-run-dir D:\AgriFusion-IoT\Backend\Benchmark\context_classifier\outputs_option2_4class\training\27-05-2026\context_train_125148
```

Train only the tabular ladder:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\context_classifier\train.py --experiment-names v0 v1 v2 v3 --model-names xgboost tabnet_classifier
```

Run a training smoke test:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\context_classifier\train.py --smoke-test
```

Backfill scientific artifacts for an existing training run without retraining:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\context_classifier\backfill_training_artifacts.py --train-run-dir D:\AgriFusion-IoT\Backend\Benchmark\context_classifier\outputs_option2_4class\training\<DD-MM-YYYY>\context_train_<HHMMSS>
```

Console progress:

- the training pipeline now prints the active label scheme, experiment name, and model start/finish state
- `TabNet` and `LSTM` print epoch-level progress with train loss, validation loss, validation macro-F1, and test macro-F1
- `FT-Transformer` prints epoch-level progress with train loss, validation loss, validation macro-F1, and test macro-F1
- `XGBoost` prints explicit `fitting` and `completed` messages
- PyTorch models also print the selected `device` (`cpu` or `cuda`) and CUDA runtime at training start
- after a successful training run, the pipeline also backfills prediction-level scientific artifacts automatically so later report requests do not require retraining

By default, `--smoke-test` only trains:

- `v0` for `XGBoost` and `TabNet`
- `sequence` for `LSTM`

This keeps the validation pass fast while still touching the main tabular and sequence model families.

Legacy build compatibility:

- older build runs under `outputs/` may not contain `label_scheme` or `class_names` in `dataset_manifest.json`
- the training loader now falls back to `context_label_summary.json` to infer the correct label scheme and class ordering
- this keeps older 5-class runs usable while allowing new 4-class runs to stay in `outputs_option2_4class/`

## Assumptions

- Real rows are split first using chronological order and a purge gap.
- The default split mode is `coverage_aware_temporal` so validation/test retain more real abnormal coverage when possible.
- Synthetic rows are added only into the train split.
- Real-only and synthetic-only canonical snapshots are materialized explicitly so label provenance can be inspected without re-splitting in memory.
- The build cannot start until a real labeled CSV with `big_label` and the telemetry-gap/provenance fields emitted by `fuzzy_logic_basic/real_event_labeling` exists.
- `TabNet`, `FT-Transformer`, and `XGBoost` will consume the same split-specific `v0/v1/v2/v3` tabular exports in the active augmented-tabular pipeline.
- `v0` = raw full sensor set: `soil_temp`, `soil_humidity`, `air_temp`, `air_humidity`, `EC`, `pH`, `N`, `P`, `K`.
- `v1` = raw core sensor set: `soil_temp`, `soil_humidity`, `air_temp`, `air_humidity`, `EC`.
- `v2` = `v1` + `delta_1step` + the historical 3h contract: `air_temp_slope_3h`, `air_temp_range_3h`, `air_temp_mean_3h`, `soil_temp_slope_3h`, `soil_humidity_slope_3h`, `soil_humidity_range_3h`, `EC_slope_3h`, `EC_range_3h`.
- `v3` = `v2` + the historical 8h contract: `air_temp_slope_8h`, `air_temp_range_8h`, `soil_temp_slope_8h`, `soil_temp_mean_8h`, `soil_humidity_slope_8h`, `soil_humidity_range_8h`, `EC_slope_8h`, `EC_range_8h`.
- `LSTM` will consume split-specific sequence exports, not the same tabular `v0/v1/v2/v3` ladder.
- `train_augmented_tabular.py` is the fastest safe entrypoint when the goal is to retrain the augmented tabular models on the real+synthetic dataset.
- Current training defaults use `100` max epochs for `TabNet`, `FT-Transformer`, and `LSTM`; early stopping still applies.
- `TabPFN` remains available through the broader training pipeline, but `train_augmented_tabular.py` no longer includes it in the default augmented-tabular workflow.
- The scientific-artifact backfill reuses saved model checkpoints and build splits; it does not retrain models.
- Packet-loss and ad-hoc interaction features are retained in canonical/debug outputs only; they are not part of the main `v0/v1/v2/v3` ladder.
- `five_class_v1` keeps separate `rain_humid_context` and `fertigation_spike` o nhanh legacy.
- `option2_4class` merges them into `rain_or_fertigation_context` va day la contract active hien tai.
- The training pipeline currently compares:
  - `XGBoost` on tabular `v0/v1/v2/v3`
  - `TabNet` on tabular `v0/v1/v2/v3`
  - `FT-Transformer` on tabular `v0/v1/v2/v3`
  - `LSTM` on `sequence_long`
- The report pipeline compares complete training runs across label schemes and converts them into academic charts and summary tables.

## Risks And Limits

- Real label mapping collapses some operational labels into `packet_loss` for now.
- Sequence export is emitted in long format and still needs a training-side tensorization step.
- Real rows do not yet carry explicit episode ids, so the current split is chronological with purge gap rather than fully episode-aware.
- The build consumes only `synthetic_flb_gap_aware.csv`; `synthetic_flb_input_labeled.csv` remains a simulator-side auxiliary artifact and is not part of this benchmark contract.
- `v2` and `v3` intentionally follow the older direct-benchmark window contracts so their metrics can be compared back to the earlier runs.
- `suspected_cause` for packet loss is currently a heuristic proxy meant for interpretation, not a supervised target.
- If `flb_input_with_events.csv` has never been created for the current workspace, build-time failure is expected until `fuzzy_logic_basic/real_event_labeling` is run or another labeled real CSV is supplied explicitly.
- Scientific-artifact backfill depends on the saved model artifact, `run_config.json`, `training_report.json`, and the original `build_run_dir` still existing on disk.
