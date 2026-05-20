# Maintenance

## Purpose

This folder holds utility scripts for repository housekeeping and output organization.

## Scripts

- `organize_outputs_by_date.py`
  - reorganize benchmark run folders into date buckets and rewrite moved paths inside report files

## Input

- existing benchmark output roots under `pretrain/outputs`, `v1/outputs`, and `v2/outputs`

## Output

- date-bucketed output folders such as `outputs/DD-MM-YYYY/<run_name>`

## Command Example

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\maintenance\organize_outputs_by_date.py
```

## Assumptions

- The script is run on already-generated benchmark outputs.
- It only moves folders that match the expected run-id pattern.

## Risks / Limits

- This is a filesystem reorganization tool.
- If a target folder already exists, the corresponding move is skipped.
- The script rewrites stored path strings inside some report files after moving runs.
