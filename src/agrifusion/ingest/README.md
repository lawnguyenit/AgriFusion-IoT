# Layer0 Ingestion

## 1. Purpose

`src/agrifusion/ingest` is the standard package for bringing
source telemetry into local raw artifacts that can be audited and
replayed.

It does not perform analytical preprocessing. Its job is to:

- determine whether source data is new or duplicated
- fetch the latest payload
- persist raw history to disk
- persist metadata and sync state

## 2. Active Structure

```text
ingest/
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
- `.env` (repo root; legacy `Backend/.env` is still read)
- CLI parameters from `src/agrifusion/cli.py`

## 4. Outputs

- `output/Layer0/Firebase_data/new_raw/latest.json`
- `output/Layer0/Firebase_data/new_raw/latest_meta.json`
- `output/Layer0/Firebase_data/new_raw/source_manifest.json`
- `output/Layer0/Firebase_data/new_raw/source_snapshot.json`
- `output/Layer0/Firebase_data/new_raw/sync_state.json`
- `output/Layer0/Firebase_data/history/**`
- `output/Layer0/Firebase_data/raw_history/**` when full history
  is requested; this content-addressed archive preserves the source record
  before Core normalization, including long firmware/hyperparameter logs

## 5. Reproducibility

Fetch latest from Firebase:

```powershell
agrifusion --only-layer0 --source firebase --node-id Node2
```

Fetch full history from Firebase:

```powershell
agrifusion --only-layer0 --source firebase --node-id Node2 --full-history
```

Use a JSON export file:

```powershell
agrifusion --only-layer0 --source json-export --input-json C:\path\export.json --node-id Node2 --full-history
```

## 6. Notes

- `Layer0IngestionPipeline` is the standard entry point.
- `latest/meta` is the primary source for deciding whether data is new.
- Raw history is immutable evidence and must stay auditable.
- The normalized `history/` files remain the Layer1 input. `raw_history/` is
  a sibling evidence archive; repeated identical source records reuse the same
  content-addressed path and are not overwritten.

## 7. Detailed Flow

For the implemented control flow and module read order, see
[FLOW.md](FLOW.md).
