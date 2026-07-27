# Benchmark To Model Suite Specification

Status: implemented system specification  
As of: July 18, 2026

This document explains the current end-to-end benchmark flow from
canonical benchmark inputs to `model_suite` training runs.

It is written for external auditors and GPT-style readers who need one
authoritative description of:

- which module owns which decision;
- how samples, features, labels, and protocol partitions are connected;
- which files are the handoff contract between `evaluation_protocols`
  and `model_suite`;
- what must not be inferred from the artifacts.

## 1. Scope

This specification covers the current benchmark-primary training lane:

- `V0`
- `V1`
- `V2 same-Y 3h`
- `V2 same-Y 8h`

Primary model training and comparison currently consume only:

- point targets for `V0` and `V1`;
- same-Y point targets for `V2`;
- source-development folds inside `P1_SOURCE`;
- frozen `P1 -> P2` target holdout evaluation.

This specification does not treat the following as primary model-suite
training scope:

- `V2 temporal` labels
- `V6-E`
- `V6-B8`
- legacy `V3`

Those artifacts may still exist in the repository, but they are not the
current benchmark-primary train lane into `model_suite`.

## 2. Authority Boundaries

The benchmark stack is intentionally split into independent lanes.

### 2.1 `dataset_views`

Responsibility:

- materialize feature matrices from canonical telemetry.

Owns:

- feature engineering
- feature schemas
- allowlisted feature columns
- row index lineage
- feature artifact hashes

Does not own:

- labels
- folds
- train/validation/test meaning
- model training

### 2.2 `weak_labels`

Responsibility:

- generate weak labels from canonical telemetry.

Owns:

- point labels for `V0` and `V1`
- same-Y labels for `V2`
- evidence flags
- intrinsic eligibility and intrinsic exclusion state
- threshold fitting for weak-label rules

Does not own:

- protocol folds
- deployment domains such as `P1_SOURCE` / `P2_TARGET`
- purge windows for evaluation folds
- model training

### 2.3 `evaluation_protocols`

Responsibility:

- define benchmark framing and convert views plus labels into runner
  manifests.

Owns:

- deployment-domain assignment
- fold definitions
- matched-cohort comparison definitions
- frozen source-to-target holdout framing
- final trainability after protocol exclusion
- runner manifests consumed by downstream trainers

Does not own:

- feature generation logic
- weak-label rule logic
- generic model-family training code

### 2.4 `model_suite`

Responsibility:

- consume a locked protocol runner and execute model training and
  evaluation.

Owns:

- model family adapters
- tabular preprocessing
- model fitting
- per-job persistence
- per-sample predictions
- pooled summaries and run reports

Does not own:

- benchmark fold construction
- sample inclusion semantics upstream of `final_trainability`
- weak-label generation
- feature materialization

## 3. End-To-End Flow

The implemented flow is:

1. Canonical benchmark source is frozen outside `model_suite`.
2. `dataset_views` materializes feature views keyed by canonical record
   identity.
3. `weak_labels` materializes auditable label artifacts from the same
   canonical source.
4. `evaluation_protocols` resolves:
   - which deployment each sample belongs to;
   - which fold and partition it belongs to;
   - whether it is protocol-eligible;
   - whether it is finally trainable;
   - which feature artifact and label artifact authority apply.
5. `evaluation_protocols` writes runner manifests under:
   - `primary_protocol/runner/`
6. `model_suite` loads those manifests and trains models strictly from
   the resolved rows in the runner contract.
7. `model_suite` writes job artifacts, prediction artifacts, summary
   tables, and run metadata under its own artifact root.

## 4. Canonical Sample Identity

The benchmark-primary point/window lane is record-anchored.

Canonical identity:

- `record.id`

Downstream mapping contract:

- `dataset_views` feature rows are keyed by `record.id`
- `weak_labels` point and same-Y label rows are keyed by `sample_id`
  where `sample_id == record.id`
- `evaluation_protocols` resolves training manifests on that same
  identity
- `model_suite` trains and predicts at that same sample granularity

For the active point/window lane, the generic form is:

`D(v) = {(record_id_i, X_i^(v), Y_i)}`

where:

- `v` changes only the feature representation;
- `record_id_i` remains the same anchor identity;
- `Y_i` is shared across `V0`, `V1`, and the corresponding `V2 same-Y`
  view at the same `record_id`.

## 5. Active Feature Views And Targets

### 5.1 V0

Feature view id:

- `v0_point`

Feature source view id:

- `v0_minimal_sensor`

Target task id:

- `v0_point_train`

Meaning:

- minimal current-row snapshot

### 5.2 V1

Feature view id:

- `v1_point`

Feature source view id:

- `v1_sensor_row`

Target task id:

- `v1_point_train`

Meaning:

- expanded current-row snapshot

### 5.3 V2 same-Y 3h

Feature view ids:

- `v2_same_y_mini_3h`
- `v2_same_y_full_3h`

Feature source view ids:

- `v2_minimal_sensor_window_3h`
- `v2_sensor_row_window_3h`

Target task id:

- `v2_same_y_3h`

Meaning:

- current-row prediction with causal 3-hour history features
- target is copied from the point label at the same `record.id`

### 5.4 V2 same-Y 8h

Feature view ids:

- `v2_same_y_mini_8h`
- `v2_same_y_full_8h`

Feature source view ids:

- `v2_minimal_sensor_window_8h`
- `v2_sensor_row_window_8h`

Target task id:

- `v2_same_y_8h`

Meaning:

- current-row prediction with causal 8-hour history features
- target is copied from the point label at the same `record.id`

## 6. Label Meaning In The Active Train Lane

Primary point labels are:

- `normal_point`
- `low_relative_moisture_point`
- `unknown_environment_point`

Non-train exclusion state:

- `excluded_technical_invalid`

Important:

- `V0` and `V1` must have identical `Y` by `record.id`
- `V2 same-Y` must copy the point target at the same `record.id`
- `V2 temporal` is a different label family and is not the current
  model-suite primary target family

## 7. Runner Contract Between `evaluation_protocols` And `model_suite`

This is the most important handoff in the system.

`model_suite` does not infer benchmark scope directly from raw
`dataset_views` or `weak_labels` runs. It consumes the locked runner
contract created by `evaluation_protocols`.

### 7.1 Entry files

Under:

- `Backend/Benchmark/evaluation_protocols/.../primary_protocol/runner/`

the required inputs are:

- `task_view_registry.csv`
- `task_training_manifest.parquet`
- `comparison_training_manifest.parquet`
- `frozen_target_manifest.parquet`
- `runner_contract.json`

### 7.2 `task_view_registry.csv`

Purpose:

- explicit mapping between a trainable experiment view, its feature
  artifact authority, and its label-task authority.

Key columns:

- `feature_view_id`
- `feature_source_view_id`
- `label_task_id`
- `protocol_view_id`
- `feature_artifact_path`
- `allowed_feature_columns_json`
- `identifier_columns_json`
- `audit_only_columns_json`
- `forbidden_columns_json`

Meaning:

- this file tells `model_suite` which physical feature artifact belongs
  to each benchmark view and which columns are allowed as model inputs.

### 7.3 `task_training_manifest.parquet`

Purpose:

- authoritative row-level task manifest for source folds and target
  holdout.

Each row represents a resolved benchmark sample with protocol meaning.

Key columns:

- `sample_id`
- `feature_view_id`
- `fold_id`
- `partition`
- `deployment_domain`
- `label_name`
- `label_status`
- `intrinsic_eligibility`
- `protocol_eligibility`
- `final_trainability`
- feature lineage hashes and artifact paths

Meaning:

- `weak_labels` decides intrinsic label state
- `evaluation_protocols` decides protocol inclusion
- `final_trainability` is the downstream gate used by
  `model_suite`

### 7.4 `comparison_training_manifest.parquet`

Purpose:

- authoritative matched-cohort manifest for same-Y comparisons.

Key additional columns:

- `comparison_id`
- `comparison_side`
- `matched_cohort_id`
- `record_id_order`
- `record_set_hash`

Meaning:

- both comparison sides are already aligned upstream
- `model_suite` trains each side separately, but the comparison cohorts
  are resolved by `evaluation_protocols`, not by the trainer

### 7.5 `frozen_target_manifest.parquet`

Purpose:

- single-refit source-to-target manifest for frozen `P1 -> P2`
  evaluation.

Current implemented behavior:

- source rows are deduplicated across primary source folds into one
  final source training set;
- target rows are all eligible `P2 target_test` rows for each feature
  view.

Important:

- this file is a holdout evaluation contract
- it is not automatically a matched snapshot-vs-history comparison

## 8. What `evaluation_protocols` Resolves Before Training

Before `model_suite` sees a sample, `evaluation_protocols` has already
resolved:

- deployment domain
- fold id
- partition
- purge exclusion for V2 folds
- protocol eligibility
- final trainability
- matched comparison cohorts
- feature artifact authority
- label artifact authority

Therefore `model_suite` must treat the runner manifests as the single
source of truth for row inclusion.

## 9. How `model_suite` Consumes The Runner

Primary entrypoints:

- [protocol_loader.py](D:/AgriFusion-IoT/Backend/Benchmark/model_suite/data/protocol_loader.py)
- [scope_resolver.py](D:/AgriFusion-IoT/Backend/Benchmark/model_suite/data/scope_resolver.py)
- [orchestration.py](D:/AgriFusion-IoT/Backend/Benchmark/model_suite/pipeline/orchestration.py)
- [native_runner.py](D:/AgriFusion-IoT/Backend/Benchmark/model_suite/pipeline/native_runner.py)
- [training_job.py](D:/AgriFusion-IoT/Backend/Benchmark/model_suite/pipeline/training_job.py)

Actual load sequence:

1. `load_protocol_runner()` reads:
   - `task_view_registry.csv`
   - `task_training_manifest.parquet`
   - `comparison_training_manifest.parquet`
   - `frozen_target_manifest.parquet`
2. `load_stage_specs_for_profile()` reads the selected
   `model_suite/config/training_profiles.yaml`.
3. `build_stage_run_frames()` resolves the stage into concrete model
   jobs using the loaded manifests.
4. `run_protocol_model_job()` trains one model on one stage/view/fold
   scope.

## 10. Training Profiles

Current important profiles are:

- `phase1_primary_tasks`
- `phase1_primary_comparisons`
- `phase2_frozen_target_holdout`
- `full_benchmark_v0_v2`

Interpretation:

- `phase1_primary_tasks`
  - source-only task benchmark
- `phase1_primary_comparisons`
  - matched same-Y representation comparisons
- `phase2_frozen_target_holdout`
  - frozen `P1 -> P2` evaluation
- `full_benchmark_v0_v2`
  - combined execution of the three stages above

## 11. What Happens Inside One Model Job

Within `run_protocol_model_job()`:

1. rows are restricted to required partitions for that job
2. rows must satisfy `final_trainability == True`
3. allowed feature columns are taken from the registry row
4. the feature matrix is loaded from the resolved feature artifact
5. preprocessing is fit on train rows only
6. the estimator is built from the selected model profile
7. the model is fit on train rows only
8. held-out predictions are generated for the requested evaluation
   partitions
9. per-job artifacts are written

Per-job persisted files may include:

- `<model_key>.joblib`
- `model_bundle.joblib`
- `model_manifest.json`
- `preprocessing_metadata.json`
- `metrics.json`
- `training_console.log`

## 12. Output Layers Produced By `model_suite`

At the run level:

- `run_manifest.json`
- `artifact_catalog.csv`

At the profile level:

- `training_summary.csv`
- `training_validation.csv`
- `per_sample_predictions.csv`
- `pooled_metrics.csv`
- `model_comparison_table.csv`
- `run_report.md`

At the job level:

- `profiles/<profile_name>/jobs/<stage_id>/<model_key>/...`

## 13. What Is Fixed Across Controlled Comparisons

For benchmark-primary V0/V1/V2 same-Y comparisons, the controlled
comparison principle is:

- same canonical anchor identity
- same label ontology
- same upstream protocol contract
- only the feature representation changes

Examples:

- `V0` vs `V2 mini 3h`
  - changes representation from snapshot to minimal causal history
- `V1` vs `V2 full 3h`
  - changes representation from expanded snapshot to expanded causal
    history
- `3h` vs `8h`
  - changes lookback horizon

## 14. What GPT Must Not Infer

When reading benchmark and model-suite artifacts, GPT must not infer:

- that `weak_labels` owns folds or protocol partitions
- that `dataset_views` owns labels
- that `model_suite` is allowed to reconstruct cohorts from raw feature
  files
- that `pooled_metrics.csv` is automatically the paper-primary result
- that `frozen_target_holdout` is automatically a matched comparison
- that the presence of `V2 temporal` or `V6` artifacts means they are
  active in the current primary training lane
- that absence of a class in `P2 target_test` proves the class does not
  exist agronomically in `P2`

## 15. What To Read First

If a reader wants to understand one concrete benchmark run, use this
order:

1. this file
2. `Backend/Benchmark/evaluation_protocols/README.md`
3. `.../primary_protocol/runner/runner_contract.json`
4. `.../primary_protocol/runner/task_view_registry.csv`
5. `.../primary_protocol/runner/task_training_manifest.parquet`
6. `Backend/Benchmark/model_suite/README.md`
7. the chosen `model_suite` run's `run_manifest.json`
8. the chosen `model_suite` profile outputs

If a reader wants one sentence for the full handshake:

`dataset_views` defines X, `weak_labels` defines Y,
`evaluation_protocols` defines who may train on which rows and under
which comparison contract, and `model_suite` executes model training
strictly on that locked contract.
