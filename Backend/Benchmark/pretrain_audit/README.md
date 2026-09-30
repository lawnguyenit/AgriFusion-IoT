# Pre-train audit

This lane selects feature groups from a dataset-view superset, aligns the
selected features, labels, and protocol split rows by `sample_id`, and reports
feature missingness and per-target support before fitting.

It blocks samples that cross partitions inside one fold and blocks a target
with any missing training labels. Missing validation/test labels remain
missing and are counted as unevaluable; they are never treated as negatives.
Feature registries are checked for ordered columns, selected-group values,
sample ordering, and source-row positions when those hashes are available.
External registries also carry their intake and canonical source hashes into
the audit manifest.

It writes separate selected feature, label, and split Parquet artifacts. The
audit does not fit a model and does not modify the current protocol runner;
the report status is a gate for review, not an automatic approval of a model
or research claim.

```powershell
python -m Backend.Benchmark.pretrain_audit.main `
  --feature-matrix <shared-feature-superset.parquet> `
  --feature-registry <feature-group-registry.json> `
  --labels <labels.parquet> `
  --splits <training-manifest.parquet> `
  --groups values window_3h `
  --targets target.co target.nox `
  --output-root Backend/Benchmark/pretrain_audit/artifacts
```

Use only groups present in the selected feature materialization. Set
`--max-missing-fraction` to add an explicit feature missingness limit. A
target with missing values remains missing in its selected artifact; it is
never converted to a negative label.
