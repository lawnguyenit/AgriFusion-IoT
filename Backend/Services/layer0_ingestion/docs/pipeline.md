# Layer0 Ingestion Pipeline Map

## Purpose

This pipeline synchronizes telemetry from the accepted Layer0 sources
(Firebase RTDB or JSON export) into local raw artifacts.

## Main Flow

```text
Source
-> SourceAdapter
-> latest_meta_payload
-> LatestMetaSnapshot
-> SyncDecision
-> sync_state
-> latest_current_payload
-> local artifacts
-> Layer0IngestionResult
```

## Main Components

- `pipeline.py`
  Role: orchestrates one ingestion run and returns
  `Layer0IngestionResult`.
- `sources/`
  Role: reads external or offline source payloads.
- `sync/latest_sync.py`
  Role: parses latest metadata, decides sync status, and builds
  sync-state payloads.
- `stores/`
  Role: writes latest payload/meta, history snapshots, and source audit
  artifacts.
- `utils/`
  Role: package-local technical helpers.

## Inputs

- source data from Firebase or JSON export
- runtime settings from `Backend/Config/runtime.py`
- storage helpers from `Backend/Config/storage.py`

## Outputs

- local latest payload/meta
- local history snapshots
- local sync state
- source manifest and source snapshot audit artifacts

## Limits

- If required latest-meta keys are missing, the pipeline fails early.
- Incorrect decision logic in `latest_sync.py` can still cause missed or
  redundant fetches.
- The package still supports both normalized snapshot-root payloads and
  legacy latest/current RTDB paths for compatibility with current stored
  data.
