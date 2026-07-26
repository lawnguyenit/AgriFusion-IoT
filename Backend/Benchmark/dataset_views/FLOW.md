# Dataset Views Flow

## Purpose

`dataset_views` materializes feature matrices from canonical Layer1. It
does not define benchmark folds, does not own label rules, and does not
train models.

## Entrypoint

- CLI:
  - `python Backend/Benchmark/dataset_views/main.py ...`
- Runtime:
  - `main.py -> materialize_dataset_views()`
  - `pipelines/materialize.py`

## Implemented flow

```mermaid
flowchart TD
    A["dataset_views/main.py"] --> B["Parse MaterializationConfig"]
    B --> C["Resolve selected public views"]
    C --> D["Validate view ids and mode"]
    D --> E["Load canonical history"]
    E --> F["Load feature catalog + Layer1 manifest"]
    F --> G{"Selected views need segments?"}
    G -- "Yes" --> H["Load segment manifest"]
    G -- "No" --> I["Skip segment manifest"]

    H --> J["Build row_index + metadata"]
    I --> J
    J --> K{"benchmark-ready mode?"}
    K -- "Yes" --> L["Load label artifact and validate join"]
    K -- "No" --> M["No external labels attached"]

    L --> N["Write shared outputs"]
    M --> N

    N --> O{"Has V3 views?"}
    O -- "Yes" --> P["Prepare V3 family context"]
    O -- "No" --> Q["Skip V3 context"]

    P --> R{"Has V6 views?"}
    Q --> R
    R -- "Yes" --> S["Prepare V6 family context"]
    R -- "No" --> T["Skip V6 context"]

    S --> U["Loop requested views"]
    T --> U
    U --> V{"View family?"}
    V -- "Standard row/V2" --> W["materialize_standard_view()"]
    V -- "V3 lineage" --> X["materialize_v3_view()"]
    V -- "V6 sequence" --> Y["materialize_v6_view()"]
    W --> Z["Write per-view artifacts"]
    X --> Z
    Y --> Z
```

## What comes in

- Layer1 canonical history
- Layer1 feature catalog
- Layer1 manifest
- segment manifest when V2/V3/V6 requires it
- optional explicit label artifact when mode is `benchmark-ready`

## What goes out

- `artifacts/<run_id>/shared/row_index.*`
- `artifacts/<run_id>/shared/metadata.*`
- `artifacts/<run_id>/shared/source_manifest.json`
- `artifacts/<run_id>/views/<view_id>/X.*`
- `artifacts/<run_id>/views/<view_id>/manifest.json`
- `artifacts/<run_id>/views/<view_id>/schema.json`
- family-specific audits for V2/V3/V6

## Folder map

- `pipelines/materialize.py`
  - main orchestration
- `pipelines/runtime.py`
  - taxonomy resolution and request validation
- `pipelines/shared_outputs.py`
  - row index, metadata, and shared run outputs
- `pipelines/standard_views.py`
  - dispatch for row views and V2
- `windowing/`
  - V2 continuity-aware windows
- `row_views/`
  - explicit row matrices for V0 and V1
- `pipelines/v3_family.py` + `lineage/`
  - V3 operational-lineage
- `pipelines/v6_family.py` + `v6_environment/`
  - V6 sequence lane

## Logic boundaries

- view selection and taxonomy live in `configs/` and `runtime.py`
- orchestration lives in `pipelines/`
- domain-family logic lives in `windowing/`, `lineage/`, and
  `v6_environment/`
- file writing lives in `writers/`

## What a maintainer should not infer

- `dataset_views` does not decide benchmark train/validation/test splits
- `dataset_views` does not decide final trainability
- `dataset_views` should not assign scientific meaning to labels

## Read this next

1. `main.py`
2. `pipelines/materialize.py`
3. `pipelines/runtime.py`
4. `pipelines/shared_outputs.py`
5. `pipelines/standard_views.py`
6. `windowing/engine.py`
7. `pipelines/v3_family.py` or `pipelines/v6_family.py` when needed
