# Output Cutoff Maintenance

## Purpose

`output_cutoff_maintenance/` trims local processing outputs to a fixed local-date cutoff when demo or benchmark artifacts accidentally extend beyond the intended report window.

This maintenance stage touches only local derived outputs:

- `Backend/Output_data/Layer1`
- `Backend/Benchmark/benchmark_dataset/dataset`

It does not edit Layer0 raw sources or Firebase.

## Input

- `Backend/Output_data/Layer1/*/history.jsonl`
- `Backend/Output_data/Layer1/*/latest.json`
- `Backend/Output_data/Layer1/*/state.json`
- benchmark dataset CSV and report JSON files in `Backend/Benchmark/benchmark_dataset/dataset`

## Output

- pruned `Layer1` histories and latest snapshots
- pruned benchmark CSV exports whose `timestamp` is newer than the cutoff
- refreshed row-count fields inside the affected benchmark report JSON files

## Command

```powershell
python Backend\main.py --prune-output-after-local-date 2026-05-10
```

## Assumptions

- Cutoff is interpreted in `BackendSettings.timezone`.
- The command keeps records up to `23:59:59` of the requested local date.
- `exp2` CSV artifacts are additionally cleaned with `dropna()` after the date trim so the active `v2` benchmark export does not keep incomplete lookback rows.

## Risks / Limits

- This command rewrites local output artifacts in place.
- It does not prune Layer0 raw archives, Firebase, or old training artifacts.
- If every sample of a rare label lies after the cutoff date, that label can disappear from the remaining dataset even though the taxonomy itself is unchanged.
