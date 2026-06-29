# FT-Transformer Benchmark

## Muc dich cua module

`ft_transformer_benchmark/` la benchmark downstream doc lap cho du lieu tabular tho va feature-engineered trong `Backend/Benchmark/benchmark_dataset/dataset`.

Module nay duoc tao de:
- bo sung mot nhanh `FT-Transformer` rieng, tach biet voi `tabular_benchmark`;
- tai dung cung ladder nguon du lieu `v0 -> v5` de so sanh cong bang voi `XGBoost` va cac baseline tabular khac;
- giu toan bo output, metrics va artifact trong mot folder benchmark rieng de de doi chieu khi bao cao.

Module khong tao dataset moi, khong doi split policy, va khong thay schema du lieu benchmark goc. No dung lai cung nguon CSV va cung merge label nhu `tabular_benchmark`, nhung raw tabular bundle hien duoc dat o `Backend/Benchmark/common/raw_tabular_dataset.py`.

## Input

Input mac dinh:
- `Backend/Benchmark/benchmark_dataset/dataset/benchmark_input_aligned.csv`
- `Backend/Benchmark/benchmark_dataset/dataset/benchmark_input_labeled.csv`
- cac CSV feature-engineered da co:
  - `single_window_exp2.csv`
  - `single_window_exp6.csv`
  - `multi_window_combo2.csv`

Ladder thi nghiem:
- `v0`: full Layer1 raw sensor + chemistry schema
- `v1`: Layer1 environment + EC raw ablation
- `v2`: 3h single-window feature arm
- `v3`: delta + 3h + 8h combo arm
- `v4`: full single-window engineered arm
- `v5`: union Layer1 raw + full single-window engineered arm

## Output

Moi run sinh ra:
- `outputs/DD-MM-YYYY/ft_transformer_<run_id>/aggregate_model_metrics.csv`
- `training_report.json`
- `run_config.json`
- `run_status.json`
- `best_result.txt`
- `experiments/<experiment_name>/direct_dataset.csv`
- `experiments/<experiment_name>/feature_schema.json`
- `experiments/<experiment_name>/models/*.pt|*.joblib`
- `experiments/<experiment_name>/scientific_artifacts/ft_transformer_classifier/scientific_manifest.json`
- `experiments/<experiment_name>/scientific_artifacts/ft_transformer_classifier/training_history.csv`
- `experiments/<experiment_name>/scientific_artifacts/ft_transformer_classifier/scalar_metrics.csv`
- `experiments/<experiment_name>/scientific_artifacts/ft_transformer_classifier/classwise_metrics.csv`
- `experiments/<experiment_name>/scientific_artifacts/ft_transformer_classifier/confusion_matrix.csv`
- `experiments/<experiment_name>/scientific_artifacts/ft_transformer_classifier/pr_curve_points.csv`
- `experiments/<experiment_name>/scientific_artifacts/ft_transformer_classifier/roc_curve_points.csv`
- `experiments/<experiment_name>/scientific_artifacts/ft_transformer_classifier/calibration_curve_points.csv`
- `experiments/<experiment_name>/scientific_artifacts/ft_transformer_classifier/{train,validation,test}_prediction_records.csv`

Moi experiment giu:
- dataset da gan split va label;
- scaler / imputer;
- artifact cua `FT-Transformer`;
- artifact cua cac baseline sklearn duoc chon.
- voi `FT-Transformer`, moi lan train lai se giu them artifact khoa hoc o muc prediction-level de co the lap lai chart va bang cho paper ma khong phu thuoc log console.

Report artifact:
- `reports/DD-MM-YYYY/ft_report_<run_id>/combined_model_metrics.csv`
- `summary_model_metrics.csv`
- `scientific_scalar_metrics.csv`
- `report_summary.md`
- cac bieu do PNG:
  - `chart_test_macro_f1.png`
  - `chart_test_accuracy.png`
  - `chart_<run_label>_feature_ladder_macro_f1.png`
  - `chart_<run_label>_feature_ladder_accuracy.png`
  - `chart_<run_label>_<experiment>_<model>_curves.png`
  - `chart_<run_label>_<experiment>_<model>_diagnostics.png`
  - `chart_<run_label>_<experiment>_<model>_test_confusion.png`
  - `chart_<run_label>_<experiment>_<model>_test_pr_curve.png`
  - `chart_<run_label>_<experiment>_<model>_test_roc_curve.png`
  - `chart_<run_label>_<experiment>_<model>_test_calibration.png`

## Command chay neu co

Chay mac dinh:

```powershell
python -m Backend.Benchmark.ft_transformer_benchmark.main
```

Chay subset thi nghiem:

```powershell
python -m Backend.Benchmark.ft_transformer_benchmark.main --experiments v1 v3 v5
```

Chay subset model:

```powershell
python -m Backend.Benchmark.ft_transformer_benchmark.main --model-names xgboost ft_transformer_classifier
```

Smoke-test nhanh:

```powershell
python -m Backend.Benchmark.ft_transformer_benchmark.main --smoke-test
```

Console progress:

- the pipeline prints run start, current experiment, and model start/finish state
- `ft_transformer_classifier` prints epoch-level progress with train loss, validation loss, validation macro-F1, and test macro-F1
- sklearn-family baselines such as `xgboost` print explicit `fitting` and `completed` messages
- PyTorch models print the selected `device` (`cpu` or `cuda`) and CUDA runtime at training start

Sinh report tu mot hoac nhieu run da train:

```powershell
python -m Backend.Benchmark.ft_transformer_benchmark.report --run-dir D:\AgriFusion-IoT\Backend\Benchmark\ft_transformer_benchmark\outputs\27-05-2026\ft_transformer_123456
```

So sanh nhieu run:

```powershell
python -m Backend.Benchmark.ft_transformer_benchmark.report ^
  --run-dir D:\AgriFusion-IoT\Backend\Benchmark\ft_transformer_benchmark\outputs\27-05-2026\ft_transformer_123456 ^
  --run-label smoke ^
  --run-dir D:\AgriFusion-IoT\Backend\Benchmark\ft_transformer_benchmark\outputs\27-05-2026\ft_transformer_130500 ^
  --run-label full
```

## Artifact khoa hoc de dua vao paper

Sau khi retrain bang pipeline hien tai, nhanh `FT-Transformer` se tu luu:

- history theo epoch:
  - `train_loss`, `validation_loss`
  - `validation_macro_f1`, `test_macro_f1`
  - `attention_entropy`, `grad_norm`, `cls_norm`, `token_std`, `epoch_seconds`
- metrics tong hop theo split:
  - `accuracy`, `balanced_accuracy`, `macro_f1`, `weighted_f1`
  - `log_loss`
  - `ovr_macro_roc_auc`
  - `ovr_macro_average_precision`
  - `ovr_macro_brier`
  - `top1_ece_15bins`
- prediction-level records:
  - `timestamp`
  - `y_true`, `y_pred`
  - `top1_confidence`, `confidence_margin`, `prediction_entropy`
  - probability cho tung class
- artifact duong cong:
  - PR curve
  - ROC curve
  - calibration curve
- artifact danh gia:
  - confusion matrix
  - classwise precision/recall/F1/support

Neu run cu duoc train truoc khi co he thong nay, cac artifact tren se khong day du. Khi do can retrain de sinh lai full artifact.

## Gia dinh xu ly

- Split train/validation/test van bam theo benchmark raw tabular hien co va dung cung split policy voi `tabular_benchmark`.
- Label downstream van bam vao `benchmark_input_labeled.csv` va cung rule chon label voi nhanh raw benchmark hien tai.
- FT-Transformer chi xu ly numeric tabular features, nen du lieu duoc median-impute va standardize truoc khi train.
- Categorical embedding chuyen biet chua duoc them vi ladder `v0-v5` hien chu yeu la feature so hoac co 0/1 co the xem nhu numeric token.

## Rui ro hoac gioi han hien tai

- FT-Transformer trong module nay la ban tu cai dat toi gian bang PyTorch de phuc vu hoc va benchmark, chua nham tai hien toan bo bien the toi uu trong paper goc.
- Do tai dung ladder `v0-v5`, chat luong mo hinh van phu thuoc manh vao scarcity cua label abnormal trong split validation/test.
- Report artifact hien tai da du manh de lap hinh va bang cho FT-Transformer benchmark, nhung cac run cu truoc khi them `scientific_artifacts/` se can retrain de co du file prediction-level va curve-level.
