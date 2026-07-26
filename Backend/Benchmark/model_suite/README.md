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

- `run_manifest.json`
- `artifact_catalog.csv`
- `smoke_protocol/smoke_model_summary.csv`
- `smoke_protocol/smoke_model_validation.csv`
- `smoke_protocol/per_sample_predictions.csv`
- `smoke_protocol/pooled_metrics.csv`
- `smoke_protocol/model_comparison_table.csv`
- `smoke_protocol/smoke_report.md`

Non-smoke profile runs emit profile-scoped outputs under:

- `profiles/<profile_name>/training_summary.csv`
- `profiles/<profile_name>/training_validation.csv`
- `profiles/<profile_name>/per_sample_predictions.csv`
- `profiles/<profile_name>/pooled_metrics.csv`
- `profiles/<profile_name>/model_comparison_table.csv`
- `profiles/<profile_name>/run_report.md`
- `profiles/<profile_name>/jobs/<stage_id>/<model_key>/...`

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
