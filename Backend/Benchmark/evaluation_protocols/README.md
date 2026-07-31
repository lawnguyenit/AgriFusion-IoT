# Evaluation Protocols

`Backend/Benchmark/evaluation_protocols` is an independent benchmark
lane for source-development and cross-position transport evaluation.

It is intentionally separate from:

- `dataset_views/`, which materializes benchmark-ready views; and
- `weak_labels/`, which acts as the weak-label authority lane.

Its responsibilities are:

- define deployment domains such as `P1_SOURCE` and `P2_TARGET`;
- consume environment and stage authority from an explicit upstream
  `protocol_registry` run;
- consume the upstream Phase A fold contract with 7-day primary and
  5-day diagnostic policy;
- describe E3 only as protocol-locked re-evaluation on a previously exposed
  target;
- freeze source-fitted threshold policy for later transport analysis;
- emit split manifests, fold diagnostics, runner manifests, and
  transport-shift reports.

Current output layout distinguishes:

- `ARTIFACT_GUIDE.md`: reader-first map of what the run takes in, does,
  and writes out;
- `run_metadata/`: run manifest, validation report, and artifact index;
- `domain_manifests/`: deployment-domain ownership and protocol framing;
- `validity_diagnostics/`: benchmark-validity audits for representation
  and estimability that sit above the raw runner manifests;
- `primary_protocol/`: the locked 7-day primary Fold 01 artifact,
  split into `folds/`, `cohorts/`, `lineage/`, and `runner/`;
- `temporal_diagnostics/support_5day/`: non-primary 5-day support
  diagnostics and full assignment audits;
- `temporal_diagnostics/secondary_7day/`: 7-day fold diagnostics;
- `transport_diagnostics/`: feature-shift and frozen-label transport
  reports;
- `threshold_diagnostics/`: frozen q10 policy and Q05/Q10/Q15/Q20
  sensitivity diagnostics;
- `dependency_manifests/`: auditable support files used to explain or
  verify the main protocol.

The current artifact runs also write short `README.md` guides inside the
main output groups so a returning reader can re-enter the project by
opening the folder itself rather than reverse-engineering the code.

Code layout is responsibility-first:

- `domains/`: deployment-domain mapping and threshold-freezing policy;
- `diagnostics/`: fold support, sensitivity, shift, and dependency
  diagnostics;
- `lineage/`: split-aware assignment construction, matched cohorts,
  and primary protocol selection;
- `pipeline/`: orchestration and artifact layout only.

It may consume outputs from `weak_labels`, but it must not be nested
inside `weak_labels` because protocol framing is a separate benchmark
concern from label construction.

Governed execution now requires `--protocol-registry-run-dir`. A Phase A
registry has `phase_a_only=true`, so this lane fails closed until Phase B
publishes a frozen registry. This prevents the historical runner contract from
silently overriding the corrected 7-day/5-day policy.

It also consumes an explicit `dataset_views` artifact run as the
feature authority. The runner contract must pin resolved feature
artifacts, row-index lineage, and allowlisted columns from that run
rather than inferring feature bundles from placeholders.

For downstream model training, the runner-facing authority is under
`primary_protocol/runner/`:

- authoritative benchmark scope here is `V0`, `V1`, and `V2 same-Y`
  `3h` only;
- `V2 same-Y 8h` remains available for diagnostics and sensitivity,
  but it is not part of the default public runner contract;
- `task_view_registry.csv`: explicit mapping between feature views,
  label tasks, protocol views, and resolved feature artifacts from the
  linked `dataset_views` run;
- `task_training_manifest.parquet`: one row per
  `(feature_view_id, fold_id, partition, sample_id)` with intrinsic
  state, protocol state, resolved feature lineage, hashes, and final
  trainability;
- `comparison_training_manifest.parquet`: matched-cohort runner manifest
  keyed by `(comparison_id, feature_view_id, fold_id, partition,
  sample_id)` for same-Y comparisons;
- `frozen_target_manifest.parquet`: single-refit source-to-target
  manifest for the final `P1 -> P2` zero-shot evaluation, distinct from
  pooled fold outputs;
- `task_training_manifest_validation.csv`: assertions that the manifest
  did not silently drop protocol-eligible samples.
- `comparison_training_manifest_validation.csv`: assertions that the
  comparison manifest resolves every matched cohort row back to the base
  training manifest.
- `frozen_target_manifest_validation.csv`: assertions that every primary
  feature view has both final source-fit rows and `P2 target_test` rows.
- `validity_diagnostics/representation/class_specific_retention.csv`:
  class-specific retention from native task cohorts to matched same-Y
  cohorts.
- `validity_diagnostics/representation/native_vs_matched_distribution.csv`:
  native-versus-matched class-distribution distortion by comparison
  side.
- `validity_diagnostics/representation/representation_validity_report.md`:
  human-readable summary of class-selective attrition under matched
  same-Y comparisons.
- `validity_diagnostics/evaluation/estimability_matrix.csv`:
  normalized `TRAINABLE` / `SELECTABLE` /
  `FULLY_ESTIMABLE` / `PARTIALLY_ESTIMABLE` / `NOT_ESTIMABLE`
  states by partition and cohort.

The optional smoke-train audit remains a post-protocol consumer under
`primary_protocol/runner/smoke_train/`. Its authoritative outputs are:

- `smoke_training_summary.csv`: run-level trainability and held-out
  metrics;
- `smoke_training_validation.csv`: partition, class-support, and
  matched-cohort assertions;
- `per_sample_predictions.csv`: held-out prediction rows for direct
  audit and pooled reporting;
- `pooled_oof_metrics.csv`: pooled held-out metrics across folds for a
  given stage/run scope;
- `smoke_readiness_report.json`: smoke-only readiness state, separate
  from full benchmark readiness.

The authoritative full benchmark runner lives under
`primary_protocol/runner/full_train/`. Its key outputs are:

- `full_training_summary.csv`: stage-level task and comparison metrics
  for the locked primary benchmark;
- `full_training_validation.csv`: partition, class-support, and
  matched-cohort assertions for the full runner;
- `per_sample_predictions.csv`: held-out per-sample predictions for
  audit and pooled analysis;
- `pooled_oof_metrics.csv`: pooled held-out metrics across folds for
  the full primary benchmark;
- `full_readiness_report.json`: machine-readable full benchmark gate
  result.

For external review or GPT-assisted audit, start with:

- `run_metadata/benchmark_readiness_report.md`
- `run_metadata/protocol_validation_report.json`

The Markdown report is the single-file human-readable summary; the JSON
report remains the machine-readable gate authority.

## Detailed Flow

For the implemented build order from canonical data and linked artifact
runs to runner manifests, see [FLOW.md](FLOW.md).
