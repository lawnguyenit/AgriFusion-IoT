# External feature processing

This lane reads an `external_intake` canonical candidate and its run manifest,
then selects only source-adapter measurement columns for X. It keeps observed
values and adds trailing 3h/8h mean, standard deviation, minimum, maximum, and
observation-count features by default. Windows are causal and grouped by the
source entity where the adapter defines one.

Criterion measurements and post-hoc operational evidence stay in the intake
canonical artifact and do not enter the feature superset. The registry stores
the selected column groups and value hashes for downstream pre-train audits.

```powershell
python -m Backend.Benchmark.external_features.main `
  --canonical <intake-run>/canonical.parquet `
  --intake-manifest <intake-run>/run_manifest.json `
  --output-root Backend/Output_data/wade_external_validation_pack/processed/features
```

Use `--window-hours` to request another explicit set of durations and
`--min-window-observations` to set the minimum evidence count. This step does
not assign labels or fit models.

External q/τ label candidates are built in the separate
[`external_labels`](../external_labels/README.md) lane. Candidate labels and
the feature superset join only by `sample_id` in the pre-train audit.
