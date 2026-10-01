# Independent multi-label model lane

This additive lane keeps the existing scalar-label model suite unchanged. It
trains one binary estimator per target from a completed pre-train audit and
supports both a single binary target and multiple independent heads. Each head
receives the same audited feature selection while its training mask can be
shared or target-specific under the audit's declared policy.

For audits configured with `training_label_policy=per_head_known`, each head
uses its own known-label training rows and independently fitted preprocessing;
the UCI CO and NOx heads can therefore retain distinct training cohorts.
Complete-case audits remain supported for the legacy shared-cohort policy.

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
When source timestamps are present, the run also writes UTC-day cluster
bootstrap intervals for log loss, Brier score, AP, and ROC-AUC. If source
entities are present, `per_entity_metrics.csv` reports support and marks
single-class entity/partitions as not discrimination-estimable while retaining
Brier and log-loss whenever known predictions exist.

For external sensor prediction, add `--require-observable-features` so fitting
and scoring require at least one selected feature to be observed. Rows with no
selected X remain in the output as `MODEL_ABSTAIN_NO_X`; they are excluded from
the primary known-truth metric cohort rather than filled by the median
imputer. Metrics and the UTC-day bootstrap use known truth AND observable X,
with abstention counts reported separately. This gate is opt-in for backward
compatibility and should be enabled for external primary runs.

The registered XGBoost and logistic profiles use balanced sample weighting by
default. For raw probabilistic-risk metrics such as log-loss and Brier, pass
`--no-use-balanced-sample-weight` so the fit does not alter the class prior
through sample weights. Record calibration separately if weighted probability
outputs are needed in a different experiment.

Stuard line/regime diagnostics use the fixed audited split and observable
training cohort; they do not refit targets or choose another split. Run
`python -m Backend.Benchmark.model_suite.multilabel.stuard_controls_main`
with the ready audit, target, and sensor-only prediction artifact to produce
global train-prior, line train-prior, sensor-only, and line-plus-sensor arms.
The line categories are learned from train only. The control manifest records
the matched evaluation sample population and a UTC-day paired bootstrap for
the line-prior versus line-plus-sensor log-loss difference.

The lane does not generate weak labels or folds. Label calibration, target
eligibility, and temporal split rules must be frozen upstream.

The final Stuard acquisition-attribution control is a four-arm nested
experiment run with `stuard_acquisition_controls_main`: `B = line_id + all six
sensor-availability flags`, then `B+soil values`, `B+environment values`, and
`B+all six values`. Every arm retains the same six availability flags, line
identity, target-known/observable cohort, and train/validation/test IDs. The
arm manifest and metrics CSV preserve exact feature names and transformed
dimensions; paired `log_loss(B)-log_loss(B+S)` contrasts and 95% UTC-day block
bootstrap intervals are emitted for validation and test. Older non-nested
control artifacts are not the final soil-versus-environment attribution.
