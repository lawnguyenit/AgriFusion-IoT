# Evaluation Protocols Flow

## Purpose

`evaluation_protocols` freezes benchmark framing into the runner
contract consumed by `model_suite`. This lane decides which rows are
trainable under which fold, partition, deployment domain, and
comparison scope.

## Entrypoint

- CLI:
  - `python Backend/Benchmark/evaluation_protocols/main.py ...`
- Runtime:
  - `main.py -> build_evaluation_protocols()`
  - `pipeline/build.py`

## Implemented flow

```mermaid
flowchart TD
    A["evaluation_protocols/main.py"] --> B["Build EvaluationProtocolConfig"]
    B --> C["Load canonical history + feature catalog"]
    C --> D["Resolve segment manifest"]
    D --> E["Create run directory + layout"]
    E --> F["Build working frame with deployment domains"]
    F --> G["Attach continuity chunks + applicability context"]
    G --> H["Split working frame into P1_SOURCE and P2_TARGET"]
    H --> I["Build 5-day and 7-day rolling fold specs"]
    I --> J["Freeze initial-source threshold context"]
    J --> K["Load linked dataset_views run"]
    K --> L["Load linked weak_labels run"]
    L --> M["Build view/task assignment artifacts"]
    M --> N["Build fold-quality diagnostics"]
    N --> O["Build matched cohorts"]
    O --> P["Build primary protocol artifacts"]
    P --> Q["Build task_view_registry"]
    Q --> R["Build task/comparison/frozen manifests"]
    R --> S["Build representation, estimability, and shift diagnostics"]
    S --> T["Write runner contract + validation report + artifact catalog"]
```

## What comes in

- Layer1 canonical history
- Layer1 feature catalog
- segment manifest
- one `dataset_views` artifact run
- one `weak_labels` artifact run

## What goes out

- `domain_manifests/deployment_domains.csv`
- `primary_protocol/folds/*`
- `primary_protocol/cohorts/*`
- `primary_protocol/runner/task_view_registry.csv`
- `primary_protocol/runner/task_training_manifest.parquet`
- `primary_protocol/runner/comparison_training_manifest.parquet`
- `primary_protocol/runner/frozen_target_manifest.parquet`
- `primary_protocol/runner/runner_contract.json`
- validity, transport, threshold, and dependency diagnostics

## Folder map

- `pipeline/build.py`
  - main orchestration
- `domains/`
  - deployment mapping and threshold freezing
- `lineage/`
  - assignments, matched cohorts, primary protocol selection
- `pipeline/consumption.py`
  - build runner-facing manifests from linked artifacts
- `diagnostics/`
  - representation, estimability, fold support, shift, dependency
- `pipeline/frozen_target.py`
  - build the final source-to-target holdout contract

## The key contract

`model_suite` must not infer train rows directly from `dataset_views` or
`weak_labels`.

It must consume:

- `task_view_registry.csv`
- `task_training_manifest.parquet`
- `comparison_training_manifest.parquet`
- `frozen_target_manifest.parquet`
- `runner_contract.json`

## Read this next

1. `main.py`
2. `pipeline/build.py`
3. `pipeline/consumption.py`
4. `lineage/assignments.py`
5. `lineage/cohorts.py`
6. `pipeline/frozen_target.py`
7. `diagnostics/representation.py`
