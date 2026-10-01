# External timestamp-block splits

This lane creates a chronological 70/15/15 holdout over linked UTC timestamp
blocks. Rows sharing the anchor timestamp or any declared source timestamp receive the same partition,
so environmental observations shared across Stuard's lines cannot cross a
partition boundary. Ratios apply to unique timestamps; row ratios can vary
slightly when entities have missing observations.

The split is an immutable, candidate artifact. It does not select labels,
evaluate support gates, or authorize model fitting. The support audit applies
the approved B2 TEMPORAL mapping before model policy review.

```powershell
python -m Backend.Benchmark.external_splits.main `
  --canonical <canonical.parquet> `
  --output-root Backend\Output_data\wade_external_validation_pack\processed\splits `
  --group-columns entity_id `
  --shared-timestamp-columns environment_timestamp,water_timestamp
```
