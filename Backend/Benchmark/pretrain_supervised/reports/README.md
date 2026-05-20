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

## Input

- pretrain run folders under `Backend/Benchmark/pretrain_supervised/pretrain/outputs`
- downstream run folders under `Backend/Benchmark/pretrain_supervised/v0..v4/outputs`
- direct benchmark run folders when report generation is pointed at them

## Output

- `charts_summary/<YYYY-MM-DD>-summary/`
- `report_pack/<YYYY-MM-DD>-pack/`
- `report_pack_lite/<YYYY-MM-DD>-pack/`
- `data_profile_report/<YYYY-MM-DD>-profile/`
- per-run `charts/` folders inside the run directory

## Command Examples

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\reports\generate_charts.py D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\v4\outputs\19-05-2026\v4_084330
python D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\reports\generate_version_summary.py --force
python D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\reports\generate_report_pack.py --lite --force
python D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\reports\generate_data_profile_report.py --force
```

## Assumptions

- The requested benchmark reports already exist.
- The script scans the latest completed run folders unless an explicit output or run path is provided.
- Charts are generated from frozen artifacts, not from raw source data.

## Risks / Limits

- These scripts are report generators only.
- Large dense charts are better kept for appendix use.
- If output folders are not present, the scripts will raise a not-found error rather than retrain anything.
