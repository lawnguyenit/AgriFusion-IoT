# Layer0 Ingestion

## 1. Purpose

`Backend/Core/layer0` is the standard package for bringing
source telemetry into local raw artifacts that can be audited and
replayed.

It does not perform analytical preprocessing. Its job is to:

- determine whether source data is new or duplicated
- fetch the latest payload
- persist raw history to disk
- persist metadata and sync state

## 2. Active Structure

```text
layer0/
|-- pipeline.py
|-- sources/
|   |-- firebase.py
|   `-- json_export.py
|-- stores/
|   |-- artifact_store.py
|   |-- telemetry_store.py
|   `-- sync_state_store.py
|-- sync/
|   `-- latest_sync.py
|-- models/
|   `-- telemetry.py
|-- utils/
`-- docs/
```

Standard flow:

```text
fetch latest meta
-> parse snapshot
-> compare with previous sync_state
-> decide whether current payload should be fetched
-> write latest/raw/history/audit artifacts
-> update sync_state
```

## 3. Inputs

- Firebase RTDB
- JSON export file
- `Backend/.env`
- CLI parameters from `Backend/main.py`

## 4. Outputs

- `Backend/Output_data/Layer0/Firebase_data/new_raw/latest.json`
- `Backend/Output_data/Layer0/Firebase_data/new_raw/latest_meta.json`
- `Backend/Output_data/Layer0/Firebase_data/new_raw/source_manifest.json`
- `Backend/Output_data/Layer0/Firebase_data/new_raw/source_snapshot.json`
- `Backend/Output_data/Layer0/Firebase_data/new_raw/sync_state.json`
- `Backend/Output_data/Layer0/Firebase_data/history/**`

## 5. Reproducibility

Fetch latest from Firebase:

```powershell
python Backend\main.py --only-layer0 --source firebase --node-id Node1
```

Fetch full history from Firebase:

```powershell
python Backend\main.py --only-layer0 --source firebase --node-id Node1 --full-history
```

Use a JSON export file:

```powershell
python Backend\main.py --only-layer0 --source json-export --input-json C:\path\export.json --node-id Node1 --full-history
```

## 6. Notes

- `Layer0IngestionPipeline` is the standard entry point.
- `latest/meta` is the primary source for deciding whether data is new.
- Raw history is immutable evidence and must stay auditable.
