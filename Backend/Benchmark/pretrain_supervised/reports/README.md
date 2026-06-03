# Reports

## Purpose

This folder groups the benchmark reporting scripts that convert existing run artifacts into Word-friendly figures and tables.

The scripts here do not train models. They only read completed benchmark outputs and materialize summary reports.

## Scripts

- `generate_charts.py`
  - render PNG charts from pretrain or downstream run folders
- `generate_version_summary.py`
  - build a version-level summary across `v0` to `v4` and render aggregate comparison charts
- `generate_report_pack.py`
  - build a Word-friendly decision pack with selected pretrain candidates, downstream roles, and per-version/per-experiment comparison charts
- `generate_data_profile_report.py`
  - build a dataset profile report for raw Firebase counts, cleaned/train-ready rows, and pre-collapse abnormal label distributions
- `generate_chapter5_evidence.py`
  - build a Chapter 5 evidence pack with split protocol, validation-vs-test model selection notes, confusion matrices, abnormal precision/recall tables, PR curves, per-sample prediction exports, and FP/FN breakdowns by original event labels
- `generate_abnormal_subgroup_benchmark.py`
  - benchmark all saved final models on decomposed abnormal groups (`big_label` and `event_primary`), with support thresholds so low-sample groups can be kept as exploratory only
- `generate_appendices_hi.py`
  - build Appendix H (benchmark protocol/model configuration) and Appendix I (full benchmark results) from the final direct/pretrain run artifacts without retraining anything

## Input

- pretrain run folders under `Backend/Benchmark/pretrain_supervised/pretrain/outputs`
- downstream run folders under `Backend/Benchmark/pretrain_supervised/v0..v4/outputs`
- direct benchmark run folders when report generation is pointed at them

## Output

- `charts_summary/<YYYY-MM-DD>-summary/`
- `report_pack/<YYYY-MM-DD>-pack/`
- `report_pack_lite/<YYYY-MM-DD>-pack/`
- `data_profile_report/<YYYY-MM-DD>-profile/`
- `chapter5_evidence/<YYYY-MM-DD>-chapter5/`
- `chapter5_evidence/<YYYY-MM-DD>-appendices-hi/`
- per-run `charts/` folders inside the run directory

## Command Examples

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\reports\generate_charts.py D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\v4\outputs\19-05-2026\v4_084330
python D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\reports\generate_version_summary.py --force
python D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\reports\generate_report_pack.py --lite --force
python D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\reports\generate_data_profile_report.py --force
python D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\reports\generate_chapter5_evidence.py --force
python D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\reports\generate_abnormal_subgroup_benchmark.py --force
python D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\reports\generate_appendices_hi.py
```

## Assumptions

- The requested benchmark reports already exist.
- The script scans the latest completed run folders unless an explicit output or run path is provided.
- Charts are generated from frozen artifacts, not from raw source data.

## Risks / Limits

- These scripts are report generators only.
- Large dense charts are better kept for appendix use.
- If output folders are not present, the scripts will raise a not-found error rather than retrain anything.
- `generate_chapter5_evidence.py` is designed for thesis-ready reporting and intentionally separates validation-selected models from exploratory best-on-test rows.
- PR curves require score-like outputs (`predict_proba`, `decision_function`, or neural logits). If a saved model cannot provide scores, the evidence pack will still export confusion/class-wise tables but skip PR data for that model.
- `generate_appendices_hi.py` assumes the final standardized-split runs already exist under the latest dated run buckets for `direct_benchmark` and `pretrain_supervised/v0..v4`, and it also expects the latest subgroup/chapter5 evidence packs to be present.
