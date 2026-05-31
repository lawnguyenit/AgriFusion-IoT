# TabPFN Benchmark

## Purpose

This module trains a `TabPFN` benchmark arm on the same raw `v0..v5` tabular ladder used by:
- `D:\AgriFusion-IoT\Backend\Benchmark\direct_benchmark`
- `D:\AgriFusion-IoT\Backend\Benchmark\ft_transformer_benchmark`

It exists to keep a separate pretrained-tabular baseline family with:
- the same data bundle contract,
- the same split policy,
- the same aggregate metric outputs,
- and the same report artifact structure.

## Input

- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_input_aligned.csv`
- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_input_with_events.csv`

The module reuses the raw-feature bundle builder from:
- `D:\AgriFusion-IoT\Backend\Benchmark\direct_benchmark`

## Output

Per run:
- `outputs\DD-MM-YYYY\tabpfn_<run_id>\aggregate_model_metrics.csv`
- `outputs\DD-MM-YYYY\tabpfn_<run_id>\training_report.json`
- `outputs\DD-MM-YYYY\tabpfn_<run_id>\run_config.json`
- `outputs\DD-MM-YYYY\tabpfn_<run_id>\run_status.json`
- `outputs\DD-MM-YYYY\tabpfn_<run_id>\best_result.txt`

Per experiment:
- `experiments\<experiment>\direct_dataset.csv`
- `experiments\<experiment>\feature_schema.json`
- `experiments\<experiment>\experiment_model_metrics.csv`
- `experiments\<experiment>\experiment_report.json`
- `experiments\<experiment>\models\*.joblib`
- `experiments\<experiment>\scientific_artifacts\...`

Report artifact output:
- `reports\DD-MM-YYYY\tabpfn_report_<run_id>\combined_model_metrics.csv`
- `reports\DD-MM-YYYY\tabpfn_report_<run_id>\summary_model_metrics.csv`
- `reports\DD-MM-YYYY\tabpfn_report_<run_id>\report_summary.md`
- charts under the same report directory

## Command

Train:

```powershell
python -m Backend.Benchmark.tabpfn_benchmark.main
```

Recommended command in this project:

```powershell
C:\Users\lawng\miniconda3\envs\ai_env\python.exe -m Backend.Benchmark.tabpfn_benchmark.main --tabpfn-model-path tabpfn-v2-classifier-v2_default.ckpt
```

If `tabpfn_classifier` is reported as unavailable, install the missing package into the exact Python env used to launch the benchmark:

```powershell
C:\Users\lawng\miniconda3\envs\ai_env\python.exe -m pip install tabpfn
```

Train a subset:

```powershell
python -m Backend.Benchmark.tabpfn_benchmark.main --experiments v1 v2 v3 --model-names xgboost tabpfn_classifier
```

Generate report artifacts:

```powershell
python -m Backend.Benchmark.tabpfn_benchmark.report --run-dir D:\AgriFusion-IoT\Backend\Benchmark\tabpfn_benchmark\outputs\DD-MM-YYYY\tabpfn_123456
```

## Assumptions

- `tabpfn` is treated as an optional dependency and is not vendored into this repo.
- The benchmark defaults to `tabpfn-v2-classifier-v2_default.ckpt` on purpose to avoid the gated browser/API-key flow of newer default model versions.
- The wrapper now row-normalizes `predict_proba` output before probability-based metrics such as `log_loss`, calibration, and Brier score are computed, so sklearn warnings about non-unit probability sums should no longer appear.
- The current implementation follows the same label policy choices as `ft_transformer_benchmark`:
  - `auto`
  - `binary`
  - `ternary`
- Data split ownership stays with the reused raw bundle pipeline.

## Risks / Current Limits

- The current environment may not have `tabpfn` installed. In that case:
  - the benchmark module still loads,
  - classical baselines can still run,
  - but `tabpfn_classifier` will be marked unavailable.
- The wrapper uses a best-effort constructor bridge because `TabPFN` API surface may differ across versions.
- If you intentionally switch back to `auto` or another gated checkpoint, TabPFN may require PriorLabs login/license acceptance or `TABPFN_TOKEN`.
- This module reuses the scalar/scientific artifact contract from the FT benchmark, but it does not produce epoch-wise training curves because `TabPFN` is not trained epoch-by-epoch inside this project.
