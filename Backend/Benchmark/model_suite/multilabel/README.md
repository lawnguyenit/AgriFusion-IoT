# Independent multi-label model lane

This additive lane keeps the existing scalar-label model suite unchanged. It
trains one binary estimator per target from a completed pre-train audit. Each
head receives the same audited feature selection and fold training cohort.

Unknown labels remain unknown. Missing truth is skipped only for that target's
evaluation metrics; it is never changed to class 0. The derived joint state is
`REF` only when every head predicts negative. Otherwise it names the positive
target set, so two simultaneous positives remain representable.

```powershell
python -m Backend.Benchmark.model_suite.multilabel.main `
  --audit-dir <ready-pretrain-audit-run> `
  --targets target.co target.nox `
  --model logistic_regression `
  --output-root Backend/Benchmark/model_suite/artifacts/multilabel `
  --threshold 0.5
```

The fixed probability threshold is configurable and stored with the run. It
is a model decision threshold, separate from the weak-label rule threshold or
persistence duration. The run stores per-head model bundles, fit and feature
hashes, per-partition probabilities/predictions, binary metrics, joint state
and metrics, charts, a report, and an artifact catalog. Completed heads are
saved and registered immediately, including when a later head fails.

The lane does not generate weak labels or folds. Label calibration, target
eligibility, and temporal split rules must be frozen upstream.
