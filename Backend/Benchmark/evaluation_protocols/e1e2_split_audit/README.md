# E1+E2 Split Audit

## Input
- one `evaluation_protocols` run for environment assignment
- one `weak_labels` run for point and `v2 same-Y` label authority

## This Utility Does
- treat `E1` and `E2` as one combined chronological source lane
- apply a simple `70/15/15` temporal split using the shared benchmark split policy
- check whether each resulting partition still contains every required class

## Output
- one artifact run under `Backend/Benchmark/evaluation_protocols/artifacts/`
- `ARTIFACT_GUIDE.md`: reader-first overview
- `run_manifest.json`: linked input runs and split config
- `task_split_summary.csv`: one row per audited task
- `task_partition_class_counts.csv`: class counts by task and partition
- `task_partition_environment_counts.csv`: `E1`/`E2` mix by task and partition
- `task_partition_ranges.csv`: timestamp boundaries for each split
