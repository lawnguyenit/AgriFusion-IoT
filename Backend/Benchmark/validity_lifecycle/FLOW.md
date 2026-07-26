# Validity Lifecycle Flow

`validity_lifecycle` is a contract-following audit lane. It does not
create new benchmark assignments; it reads the existing benchmark
contract and explains whether the current data are strong enough to
support later lifecycle experiments.

## Entry Point

- `python Backend/Benchmark/validity_lifecycle/main.py ...`

## Build Order

```mermaid
flowchart TD
    A["CLI: validity_lifecycle/main.py"] --> B["Resolve protocol run dir"]
    B --> C["Load run_manifest.json and protocol_validation_report.json"]
    C --> D["Load canonical history, task/comparison/frozen manifests"]
    D --> E["Load linked weak_labels and dataset_views artifacts"]
    E --> F["Build observation registry"]
    F --> G["Build per-view observation registry"]
    G --> H["Run support, eligibility, continuity, comparison, and dependency audits"]
    H --> I["Assemble lifecycle gates"]
    I --> J["Write CSV/Parquet outputs and validation JSON"]
    J --> K["Render English lifecycle audit report"]
```

## Internal Block Diagram

```mermaid
flowchart LR
    A["evaluation_protocols run"] --> B["loaders.py"]
    C["dataset_views run"] --> B
    D["weak_labels run"] --> B
    E["Layer1 canonical history"] --> B

    B --> F["registry.py"]
    F --> F1["observation_registry"]
    F --> F2["view_observation_registry"]

    F1 --> G["eligibility.py"]
    F1 --> H["dependencies.py"]
    F2 --> I["support.py"]
    F2 --> G
    F1 --> J["comparisons.py"]

    G --> K["reporting.py"]
    H --> K
    I --> K
    J --> K

    K --> L["validity_lifecycle_validation.json"]
    K --> M["validity_lifecycle_audit_report.md"]
```

## Output Ownership By Block

- `loaders.py`
  - no persisted outputs
  - resolves linked artifact inputs and converts them into in-memory
    frames
- `registry.py`
  - `manifests/observation_registry.parquet`
  - `manifests/observation_registry.csv`
  - `manifests/view_observation_registry.parquet`
  - `manifests/view_observation_registry.csv`
- `support.py`
  - `audits/environment_support_matrix.csv`
  - `audits/label_first_occurrence.csv`
  - `audits/class_day_segment_support.csv`
- `eligibility.py`
  - `audits/environment_eligibility_matrix.csv`
  - `audits/environment_continuity_matrix.csv`
- `comparisons.py`
  - `audits/comparison_hash_audit.csv`
- `dependencies.py`
  - `audits/ec_npk_dependency.csv`
  - `audits/ph_measurement_stability.csv`
- `reporting.py`
  - `run_metadata/validity_lifecycle_validation.json`
  - `reports/validity_lifecycle_audit_report.md`
  - `run_metadata/run_manifest.json`
  - `run_metadata/artifact_catalog.csv`

## What To Edit When A Specific Output Looks Wrong

- If `environment_support_matrix.csv` is wrong:
  - start in `registry.py` for environment assignment and target
    mapping
  - then inspect `audits/support.py`
- If `environment_eligibility_matrix.csv` is wrong:
  - inspect `registry.py` window-eligibility columns first
  - then inspect `audits/eligibility.py`
- If `comparison_hash_audit.csv` is wrong:
  - inspect `evaluation_protocols` matched cohort construction first
  - then inspect `audits/comparisons.py`
- If `ec_npk_dependency.csv` or `ph_measurement_stability.csv` is wrong:
  - inspect `registry.py` source measurement columns first
  - then inspect `audits/dependencies.py`
- If the final status in `validity_lifecycle_validation.json` is wrong:
  - inspect `reporting.py`
  - then inspect whichever upstream audit file fed the wrong gate

## Lifecycle Output Map

```mermaid
flowchart TD
    A["observation_registry"] --> B["support audit"]
    A --> C["continuity audit"]
    A --> D["proxy audits"]
    E["view_observation_registry"] --> B
    E --> F["eligibility audit"]
    G["comparison_training_manifest"] --> H["comparison_hash_audit"]
    B --> I["validation payload"]
    C --> I
    D --> I
    F --> I
    H --> I
    I --> J["validity_lifecycle_validation.json"]
    I --> K["validity_lifecycle_audit_report.md"]
```

## Core Questions

The report answers five stage questions:

1. What evidence is usable in Discovery?
2. Is Temporal falsification support actually present?
3. Does Source expansion add transport evidence or only more source
   rows?
4. What survives Deployment transport?
5. Which failures remain ambiguous and therefore require collection
   repair?
