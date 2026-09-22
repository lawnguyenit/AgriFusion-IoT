# Temporary robustness probe

This is an isolated research probe for the current weak-target direction. It
reads existing Phase B/Phase C/protocol artifacts and writes a sibling report
under `Docs/Temp`; it does not modify Core, Layer1 canonical outputs, native
label releases, protocol registries, or model-suite artifacts.

Run from the repository root:

```powershell
python -m Backend.Benchmark.temporary_robustness_probe.main
```

Outputs:

- `layer1_*.csv`: prevalence, geometry, run length, event overlap, boundary,
  and UNRES summaries;
- `layer2_metrics.csv`: one XGBoost score per representation arm and
  partition;
- `layer2_disruption_audit.csv`: evidence that the intervention preserves
  per-column missingness while changing row alignment;
- `probe_manifest.json`: source paths and the exact diagnostic contract;
- `probe_report.md`: compact handoff for the next GPT analysis.

The lane is intentionally temporary. If the direction is rejected, remove
this directory and `Docs/Temp/temporal_weak_target_probe_20260907`. If it is
accepted, migrate only the reviewed logic into the appropriate Benchmark
owner after a new decision is recorded.
