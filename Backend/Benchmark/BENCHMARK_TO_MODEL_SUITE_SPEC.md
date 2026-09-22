# Benchmark to Model Suite handoff

This document defines the boundary between benchmark construction and model
execution. It is a file-contract document, not a second training pipeline.

## Owners

- `dataset_views` owns feature materialization.
- `weak_labels` owns label authority and provenance.
- `protocol_registry` owns environment and protocol permissions.
- `evaluation_protocols` joins those inputs and freezes the runner contract.
- `model_suite` consumes the frozen runner contract and owns fitting,
  predictions, metrics and reports.

## Required upstream inputs

An evaluation-protocol run must identify:

- the canonical Layer1 history and manifest;
- the dataset-view run and feature-column contract;
- the native label release and label version;
- the protocol-registry run and authorized stage;
- the domain and fold assignments;
- the execution profile and random-seed policy.

## Runner handoff

The primary handoff is under the evaluation-protocol run directory:

```text
primary_protocol/runner/
|-- task_view_registry.csv
|-- task_training_manifest.parquet
|-- comparison_training_manifest.parquet
|-- frozen_target_manifest.parquet
`-- runner_contract.json
```

The manifests are the model-suite input. They must preserve row identity,
feature-view identity, label identity, fold/partition assignment and source
provenance. The model suite must not silently rebuild those assignments.

## Model-suite outputs

Each model job writes structured artifacts before Markdown summaries:

- run metadata and configuration;
- availability and preprocessing decisions;
- predictions and per-class metrics;
- aggregate metrics with split/fold context;
- validation, leakage and rule-control reports;
- persisted model files when the selected model supports persistence.

## Non-goals

- This handoff does not authorize mutation of Layer0 or canonical Layer1.
- A high aggregate score is not evidence of deployment generalization without
  split, provenance, leakage and domain checks.
- Analysis-only probes under `model_suite/analysis` do not automatically
  become part of the primary benchmark release.

## Useful entry points

```powershell
python -m Backend.Benchmark.evaluation_protocols.main --help
python -m Backend.Benchmark.model_suite.cli --help
```
