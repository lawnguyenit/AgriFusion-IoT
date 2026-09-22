# Backend

The backend contains two related but separate lanes:

1. **Telemetry lane** — Layer0 ingestion and Layer1 canonicalization.
2. **Research lane** — dataset views, weak labels, protocol governance,
   validity audits and model execution.

The telemetry lane does not assign benchmark labels. The research lane must
not mutate Layer0 evidence or canonical Layer1 outputs in place.

## Actual package layout

```text
Backend/
|-- main.py                         telemetry CLI
|-- Config/                         settings, paths and storage helpers
|-- Navigation/Core/                canonical Layer0/Layer1 implementation
|   |-- infrastructure/              Firebase adapter
|   |-- layer0/                      source ingestion and raw artifacts
|   |-- layer1/                      canonical telemetry processing
|   `-- layer2/                      reusable downstream feature builders
|-- Benchmark/                      research dataset/evaluation lanes
|-- Output_data/                    generated local artifacts
`-- tests/                          backend contract and processing tests
```

The canonical Python namespace for telemetry processing is
`Backend.Navigation.Core`. The old `Backend.Core` path is not supported.

## Telemetry flow

```text
Firebase RTDB or JSON export
        |
        v
Layer0IngestionPipeline
        |
        v
Backend/Output_data/Layer0/Firebase_data
        |
        v
PreprocessingPipeline
        |
        v
Backend/Output_data/Layer1/canonical
```

### Layer0 owns

- source adapters for Firebase and JSON exports;
- latest metadata and sync decisions;
- immutable raw snapshots, history and source manifests;
- replayable local evidence.

Read [Layer0 README](Navigation/Core/layer0/README.md) and
[Layer0 flow](Navigation/Core/layer0/FLOW.md).

### Layer1 owns

- canonical row construction;
- sensor/context normalization and provenance;
- continuity and temporal fields;
- field catalog and governance metadata;
- canonical persistence, quality reports and compatibility views.

Read [Layer1 README](Navigation/Core/layer1/README.md) and
[Layer1 flow](Navigation/Core/layer1/FLOW.md).

## CLI

Run from the repository root:

```powershell
python -m Backend.main --help
```

Examples:

```powershell
# Fetch current/full history and process Layer0 -> Layer1.
python -m Backend.main --source firebase --node-id Node2 --full-history

# Use an exported RTDB JSON document.
python -m Backend.main --source json-export --input-json C:\path\export.json --node-id Node2 --full-history

# Rebuild Layer1 from existing local Layer0 artifacts.
python -m Backend.main --only-layer1

# Ingestion only.
python -m Backend.main --only-layer0 --source firebase --node-id Node2
```

Runtime configuration comes from `Backend/.env` and CLI overrides. Important
settings include `EXPORT_SOURCE`, `EXPORT_NODE_ID`, `EXPORT_INPUT_JSON`,
sensor identity overrides and `FIREBASE_KEY_PATH`/`DATABASE_URL` for Firebase.

## Benchmark flow

The research lane consumes frozen Layer1 artifacts:

```text
Layer1 canonical history
        |
        +--> protocol_registry
        +--> dataset_views
        +--> weak_labels
                  |
                  v
        evaluation_protocols
                  |
        +---------+---------+
        v                   v
validity_lifecycle       model_suite
```

Read [Benchmark README](Benchmark/README.md),
[Backend pipeline flow](PIPELINE_FLOW.md), and the
[Benchmark-to-model handoff](Benchmark/BENCHMARK_TO_MODEL_SUITE_SPEC.md).

## Generated outputs

The main local outputs are:

- `Output_data/Layer0/Firebase_data/**` — raw snapshots, history, sync state
  and manifests;
- `Output_data/Layer1/canonical/**` — canonical history, latest snapshot and
  feature catalog;
- `Output_data/Layer1/segments/**` — continuity segmentation;
- `Output_data/Layer1/quality_reports/**` — data-quality and audit reports;
- benchmark run directories under the relevant lane's artifact root.

These outputs are derived evidence, not source code. Keep the raw source
immutable and write a new run/artifact when experimenting.

## Tests

See [Backend tests](tests/README.md). Focused examples:

```powershell
python -m unittest Backend.tests.test_layer1_packet_processors
python -m unittest Backend.tests.test_dataset_views_selection
python -m unittest Backend.tests.test_evaluation_protocols_smoke
python -m unittest Backend.tests.test_model_suite
```

## Boundaries

- `Backend/Config` is shared backend infrastructure, not a research-label
  owner.
- `Backend/Navigation/Core` preserves observed/provenance data and does not
  create benchmark targets.
- `Backend/Benchmark` owns labels, splits, leakage controls, training and
  scientific interpretation.
- The static frontend reads a separate `result/*` presentation contract; the
  current backend CLI does not automatically publish that contract.
