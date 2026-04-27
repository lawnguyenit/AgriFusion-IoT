# Exporters Pipeline

`Backend/Services/exporters` is the Layer 1 export package. It reads source data from Firebase RTDB or a local RTDB JSON export and writes canonical local artifacts for downstream Layer 2 preprocessing.

## Main Flow

```text
ExportPipeline
    -> sources/
    -> sync/
    -> stores/
    -> Output_data/Layer1
```

The pipeline does four things:

- reads the latest metadata and current payload from a source adapter,
- decides whether the source contains new data or only a retry/duplicate state,
- writes reproducible local artifacts,
- saves sync state so the next run can compare against the previous run.

## Package Layout

```text
exporters/
├── pipeline.py
├── sources/
│   ├── base.py
│   ├── firebase.py
│   └── json_export.py
├── stores/
│   ├── artifact_store.py
│   ├── sync_state_store.py
│   └── telemetry_store.py
├── sync/
│   └── latest_sync.py
├── models/
│   └── telemetry.py
├── utils/
│   ├── file_store.py
│   ├── json_ordering.py
│   └── layout.py
└── Explain/
    └── pipeline.md
```

The package root only keeps the public pipeline entrypoint. Source adapters, stores, sync logic, models, and utilities should be imported from their grouped packages.

## Responsibilities

### `pipeline.py`

Coordinates the full export run. It builds the source adapter, loads previous sync state, asks `sync/latest_sync.py` for a decision, writes artifacts, optionally writes full history, and returns `ExportResult`.

### `sources/`

Reads data from external or offline sources.

- `base.py`: shared snapshot normalization, source descriptors, audit artifact shape, latest-event selection.
- `firebase.py`: Firebase RTDB adapter with support for node snapshot root and legacy paths.
- `json_export.py`: local RTDB JSON export adapter.

### `sync/`

Contains the sync decision logic.

- `parse_latest_meta()`: converts latest metadata payload into a typed snapshot.
- `decide_sync()`: returns statuses such as `new_data`, `source_refresh`, `retry_waiting`, `stale_after_retry`, or `duplicate_source`.
- `build_sync_state()`: creates the next persisted sync state.

### `stores/`

Writes local Layer 1 artifacts.

- `artifact_store.py`: latest metadata, latest payload, source manifest, source snapshot.
- `sync_state_store.py`: `sync_state.json`.
- `telemetry_store.py`: current event history and optional full-history snapshots.

### `utils/`

Technical helpers with no business ownership.

- `file_store.py`: JSON writes, JSONL append, gzip, SHA-256.
- `json_ordering.py`: canonical JSON ordering for stable checksums.
- `layout.py`: timestamp formatting.

### `models/`

Small reusable telemetry helpers.

## Debug Guide

```text
Firebase cannot be read          -> sources/firebase.py
JSON export cannot be imported   -> sources/json_export.py
latest/current/history not saved -> stores/
wrong new_data/retry decision    -> sync/latest_sync.py
checksum differs unexpectedly    -> utils/json_ordering.py or utils/file_store.py
overall run order is wrong       -> pipeline.py
```

## Public Imports

Use:

```python
from Backend.Services.exporters import ExportPipeline
from Backend.Services.exporters.sources import FirebaseSourceAdapter
from Backend.Services.exporters.stores import load_sync_state
from Backend.Services.exporters.sync import decide_sync
```
