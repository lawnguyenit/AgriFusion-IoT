# Pre-train audit

This lane selects feature groups from a dataset-view superset, aligns the
selected features, labels, and protocol split rows by `sample_id`, and reports
feature missingness and per-target support before fitting.

It blocks samples that cross partitions inside one fold and blocks a target
with any missing training labels under the default `complete_case` policy. The optional
`--exclude-unknown-targets` policy removes train rows that are unknown for any
selected target. The `--training-label-policy per_head_known` policy keeps the
aligned rows and records a separate known-label training mask per target, so
independent heads may retain different rows. Both policies retain validation/test rows, including unknown truth,
for per-head prediction and metric handling. Every split row and source status
is recorded in `eligibility_audit.csv`, and estimability is recomputed on the
resulting handoff. Unknown labels are never converted to negatives.
Feature registries are checked for ordered columns, selected-group values,
sample ordering, and source-row positions when those hashes are available.
External registries also carry their intake and canonical source hashes into
the audit manifest.

When an external support-gate CSV is provided, every selected target must pass
train, validation, and test under that profile or the audit is blocked. It
writes separate selected feature, label, and split Parquet artifacts. The
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

For rule-generated unknowns, use `--exclude-unknown-targets` for a shared
complete-case cohort, or `--training-label-policy per_head_known` for
head-specific cohorts. Both retain evaluation rows and a full eligibility
ledger. Review the excluded rows and support gates before fitting.

Use only groups present in the selected feature materialization. Set
`--max-missing-fraction` to add an explicit feature missingness limit. A
target with missing values remains missing in its selected artifact; it is
never converted to a negative label.
