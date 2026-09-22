# Model Suite

`Backend/Benchmark/model_suite` owns reusable model families and
tabular training mechanics for the forward benchmark stack.

It sits beside:

- `dataset_views/`
- `weak_labels/`
- `evaluation_protocols/`

and is responsible for model-layer concerns that should not live inside
protocol construction code.

## Phase 1 scope

Current registered models:

- `dummy_majority`
- `logistic_regression`
- `extra_trees`
- `xgboost`
- `realmlp`
- `ft_transformer`
- `tabpfn`

Current availability notes:

- `realmlp` and `ft_transformer` are integrated through `pytabkit`
  adapters in the local environment.
- `tabpfn` is integrated at the adapter level but remains
  credential-gated: local non-interactive runs need either
  `TABPFN_TOKEN` or an explicit `model_path` for pretrained weights.

Current responsibilities:

- define the editable suite model catalog and run profiles under
  `config/`
- keep code-facing model registration under `registries/`
- own reusable preprocessing and persistence for tabular classifiers
- persist reusable model bundles and manifests
- support `evaluation_protocols` as a downstream consumer
- run data-backed smoke suites that emit reusable metrics,
  per-sample predictions, and artifact catalogs

The default smoke-suite config remains conservative and only includes:

- `dummy_majority`
- `logistic_regression`
- `extra_trees`
- `xgboost`

This avoids forcing heavy neural runs or `TabPFN` credential handling
into every default smoke invocation.

## Layout

- `contracts/`
  - run specs, model adapter contracts, prediction records, artifact
    references
- `data/`
  - protocol loaders, feature loaders, scope resolution, validation
- `families/`
  - model-family adapters and availability handling
- `registries/`
  - model catalog and builder registry used by the runtime pipeline
- `pipeline/`
  - protocol-native job runner, training job execution, and smoke-suite
    orchestration
- `evaluation/`
  - metrics, pooling, and cross-model comparison helpers
- `persistence/`
  - model bundle sidecars, artifact catalogs, run signatures
- `reporting/`
  - compact tables and markdown reports
- `analysis/`
  - non-mutating post-hoc analyses over existing prediction artifacts
- `analysis/k_window_variants/`
  - reproducible research benchmarks for K/representation variants, causal
    history flattening, and robustness/claim audits
- `utils/`
  - preprocessing helpers and lightweight config loading
- `config/`
  - editable JSON-in-YAML config files for model registry, profiles,
    metrics, seeds, and artifact policy
- `artifacts/`
  - versioned standalone suite runs

## Output contract

The default standalone artifact root is:

- `Backend/Benchmark/model_suite/artifacts/`

Protocol-coupled consumers such as `evaluation_protocols` may still
write model artifacts inside their own run directories, but the
underlying persistence format is owned by `model_suite`.

Each model job may emit:

- `<model_key>.joblib`
- `model_bundle.joblib`
- `model_manifest.json`
- `preprocessing_metadata.json`
- `metrics.json`
- `training_console.log`

Each standalone smoke run emits:

- `ARTIFACT_GUIDE.md`
- `run_manifest.json`
- `artifact_catalog.csv`
- `smoke_protocol/README.md`
- `smoke_protocol/smoke_model_summary.csv`
- `smoke_protocol/smoke_model_validation.csv`
- `smoke_protocol/per_sample_predictions.csv`
- `smoke_protocol/pooled_metrics.csv`
- `smoke_protocol/model_comparison_table.csv`
- `smoke_protocol/smoke_report.md`

Non-smoke profile runs emit profile-scoped outputs under:

- `ARTIFACT_GUIDE.md`
- `profiles/<profile_name>/training_summary.csv`
- `profiles/<profile_name>/training_validation.csv`
- `profiles/<profile_name>/per_sample_predictions.csv`
- `profiles/<profile_name>/pooled_metrics.csv`
- `profiles/<profile_name>/model_comparison_table.csv`
- `profiles/<profile_name>/run_report.md`
- `profiles/README.md`
- `profiles/<profile_name>/README.md`
- `profiles/<profile_name>/jobs/README.md`
- `profiles/<profile_name>/jobs/<stage_id>/<model_key>/...`

The generated guide files are intentionally short and use the same
reader-facing format as the other benchmark layers:

- input
- what this layer or folder does
- output

## Commands

Show the registered model catalog:

```powershell
python Backend\Benchmark\model_suite\cli.py --list-models
```

Show the registered training profiles:

```powershell
python Backend\Benchmark\model_suite\cli.py --list-profiles
```

Show the default artifact root:

```powershell
python Backend\Benchmark\model_suite\cli.py --show-default-artifact-root
```

Check whether selected models are available in the active environment
before launching a benchmark run:

```powershell
python Backend\Benchmark\model_suite\cli.py --check-models --model-keys dummy_majority logistic_regression xgboost ft_transformer
```

If `realmlp` is unavailable because `pytabkit` is missing in the
current environment, install it in that same environment:

```powershell
python -m pip install pytabkit
```

If `ft_transformer` is unavailable, the usual missing pieces in the
active environment are `pytabkit` and `skorch`:

```powershell
python -m pip install pytabkit skorch
```

Run the phase-1 smoke suite on an existing protocol run:

```powershell
python Backend\Benchmark\model_suite\cli.py --smoke-protocol-run-dir D:\AgriFusion-IoT\Backend\Benchmark\evaluation_protocols\artifacts\evaluation_protocols_20260717_130735
```

Run the official semantic E1 primary benchmark (Fold 01, explicit 3h arms,
registered full model defaults):

```powershell
python Backend\Benchmark\model_suite\cli.py --smoke-protocol-run-dir <E1_PROTOCOL_RUN_ROOT> --profile semantic_feature_arms_primary_3h --model-keys xgboost --no-progress
```

Run the additive temporal K-gated benchmark (native Q10-K3 temporal target;
the point/Same-Y baseline is unchanged):

```powershell
python Backend\Benchmark\model_suite\cli.py --smoke-protocol-run-dir <E1_TEMPORAL_PROTOCOL_RUN_ROOT> --profile temporal_k_gated_3h --model-keys xgboost --no-progress
```

Run the five-test history robustness and claim-audit suite:

```powershell
python Backend\Benchmark\model_suite\analysis\k_window_variants\robustness_main.py
```

The suite writes `k_robustness_audit_<run_id>` with pure-lag versus metadata
metrics, same-dimensional disrupted-order controls, `UNRES_K`/`UNRES_A`
conditional evaluation, 3-fold temporal mean±std tables, and the direct
`M_t,M_{t-1},M_{t-2}` threshold positive control. Fold 02 and Fold 03 remain
protocol-labelled diagnostics where their status requires caution; no output
changes upstream labels or canonical feature artifacts.

Run the ordered representation progression (Fold 01, fixed seed, XGBoost):

```powershell
python Backend\Benchmark\model_suite\analysis\k_window_variants\ordered_main.py
```

This writes `ordered_history_progression_<run_id>/` and trains the five
representation steps after the deterministic oracle for both K3 online and
K3 event: `M_t` (1), `X_t` (9), `M-history` (13), `X-history` (117), and
`X-history+context` (162). The final step is sensor-history plus causal 3h
context summaries and excludes acquisition/history-quality metadata.

Run the corrected nested RQ1 progression with paired risk contrasts:

```powershell
python Backend\Benchmark\model_suite\analysis\k_window_variants\rq1_main.py
```

This writes `rq1_nested_progression_<run_id>/` and evaluates
`S0=M_t -> S1=X_t -> S2=X_t+H_M -> S3=X_t+H_X -> S4=X_t+H_X+C` plus the
diagnostic `B_M=M_t+H_M` branch over protocol-owned temporal folds 01--03.
It reports fold mean/std classification metrics, macro one-vs-rest Average
Precision, per-class support, paired multiclass log-loss/Brier contrasts, and
temporal block-bootstrap intervals. The earlier ordered runner is retained as
a historical diagnostic because its `X_t -> M-history` transition was not
nested.

Run the paired causal/event target benchmark on the derived protocol:

```powershell
python Backend\Benchmark\model_suite\cli.py --smoke-protocol-run-dir <PAIRED_TARGET_PROTOCOL_RUN_ROOT> --profile temporal_event_online_3h --model-keys xgboost --no-progress
```

Compare the two trained target views on the successful-run prefix cohort
`G = {d_t < K, L_r >= K}`:

```powershell
python Backend\Benchmark\model_suite\analysis\main.py `
  --model-run-dir D:\AgriFusion-IoT\Backend\Benchmark\model_suite\artifacts\<PAIRED_MODEL_RUN_ID> `
  --target-views-artifact-dir D:\AgriFusion-IoT\Backend\Benchmark\weak_labels\artifacts\phase_c\<TARGET_VIEWS_ARTIFACT_ID> `
  --profile temporal_event_online_3h
```

This comparison requires a newly trained target-view model run because
`Y_event` and `Y_online` are different targets. The event view is retrospective
and diagnostic; future values are never passed as features.

Run the post-hoc focal analysis on the existing online-target predictions:

```powershell
python Backend\Benchmark\model_suite\analysis\main.py `
  --model-run-dir D:\AgriFusion-IoT\Backend\Benchmark\model_suite\artifacts\<PAIRED_MODEL_RUN_ID> `
  --run-depth-target-views-artifact-dir D:\AgriFusion-IoT\Backend\Benchmark\weak_labels\artifacts\phase_c\<TARGET_VIEWS_ARTIFACT_ID> `
  --profile temporal_event_online_3h `
  --partitions validation test
```

This command keeps `Y_online` unchanged and performs no new model inference.

Run the additive five-strata provenance analysis using the existing paired
online/event predictions. It does not create a five-class model; the five
strata are audit metadata over the existing three outputs:

```powershell
python Backend\Benchmark\model_suite\analysis\main.py `
  --model-run-dir D:\AgriFusion-IoT\Backend\Benchmark\model_suite\artifacts\<PAIRED_MODEL_RUN_ID> `
  --provenance-strata-target-views-artifact-dir D:\AgriFusion-IoT\Backend\Benchmark\weak_labels\artifacts\phase_c\<TARGET_VIEWS_ARTIFACT_ID> `
  --profile temporal_event_online_3h `
  --partitions validation test
```

The sibling output contains the online 5x3 matrix, event 5x3 comparator,
`U_K_succ`/`U_K_fail` K-state decomposition, per-stratum probability deltas,
transitions, and static figures. It reuses existing predictions and performs
no retraining, weight loading, or new inference.

Join an existing temporal prediction artifact to the derived UNRES origins
without retraining or rerunning inference:

```powershell
python Backend\Benchmark\model_suite\analysis\main.py `
  --model-run-dir D:\AgriFusion-IoT\Backend\Benchmark\model_suite\artifacts\<MODEL_RUN_ID> `
  --unres-origin-artifact-dir D:\AgriFusion-IoT\Backend\Benchmark\weak_labels\artifacts\phase_c\<UNRES_ORIGIN_ARTIFACT_ID>
```

The command creates a sibling
`temporal_unres_origin_prediction_join_<run_id>` folder under the model-suite
artifact root. Its default scope is the temporal 3h test partition and its
three existing prediction labels remain `LOW`, `UNRES`, and `REF`.

The flag name `--smoke-protocol-run-dir` is retained for CLI compatibility;
the `semantic_feature_arms_primary_3h` profile is non-smoke and therefore does
not receive smoke-only XGBoost overrides. The current official E1 protocol
contains only `fold_01`; secondary/legacy folds and all 8h views are excluded
from this profile. Add `logistic_regression` or `extra_trees` explicitly when
comparison models are wanted.

Run the configured R/K representation matrix (Fold 01, fixed seed, XGBoost):

```powershell
python Backend\Benchmark\model_suite\analysis\k_window_variants\configured_main.py
```

The schedule is explicit and reproducible: K1 uses R00 and R11; K3 online and
K3 event each use R00, R10, R01, and R11. R00/R10/R01/R11 contain 9/54/134/179
features respectively. The run writes a schedule, label distributions,
imbalance-aware metrics, per-class results, held-out predictions, and K3
`U_K_succ`/`U_K_fail` strata under
`Backend/Benchmark/model_suite/artifacts/k_configured_r_matrix_<run_id>/`.

Run the full primary source-only task benchmark:

```powershell
python Backend\Benchmark\model_suite\cli.py --smoke-protocol-run-dir D:\AgriFusion-IoT\Backend\Benchmark\evaluation_protocols\artifacts\evaluation_protocols_20260717_191929 --profile phase1_primary_tasks --model-keys dummy_majority logistic_regression xgboost ft_transformer
```

Run the matched-cohort same-Y comparison benchmark:

```powershell
python Backend\Benchmark\model_suite\cli.py --smoke-protocol-run-dir D:\AgriFusion-IoT\Backend\Benchmark\evaluation_protocols\artifacts\evaluation_protocols_20260717_191929 --profile phase1_primary_comparisons --model-keys dummy_majority logistic_regression xgboost ft_transformer
```

Run the frozen `P1 -> P2` target holdout benchmark:

```powershell
python Backend\Benchmark\model_suite\cli.py --smoke-protocol-run-dir D:\AgriFusion-IoT\Backend\Benchmark\evaluation_protocols\artifacts\evaluation_protocols_20260717_191929 --profile phase2_frozen_target_holdout --model-keys dummy_majority logistic_regression xgboost ft_transformer
```

Run the combined `V0/V1/V2 same-Y` benchmark across all supported
phases:

```powershell
python Backend\Benchmark\model_suite\cli.py --smoke-protocol-run-dir D:\AgriFusion-IoT\Backend\Benchmark\evaluation_protocols\artifacts\evaluation_protocols_20260717_191929 --profile full_benchmark_v0_v2 --model-keys dummy_majority logistic_regression xgboost ft_transformer
```

The CLI now shows a terminal progress UI by default:

- overall job progress bar
- current `stage/model/view/fold`
- per-job completion status
- final trained-job summary and artifact location
- model warnings and verbose trainer output are captured into
  `training_console.log` files instead of being printed into the main
  terminal stream

Disable that UI when redirecting logs or scripting:

```powershell
python Backend\Benchmark\model_suite\cli.py --smoke-protocol-run-dir D:\AgriFusion-IoT\Backend\Benchmark\evaluation_protocols\artifacts\evaluation_protocols_20260717_130735 --no-progress
```

Requested models are now validated before a smoke run starts. If one of
them is unavailable, the CLI exits early with a non-zero code and a
JSON payload explaining which dependency is missing.

## Detailed Flow

For the implemented execution path from protocol runner to per-job
artifacts and pooled reports, see [FLOW.md](FLOW.md).
