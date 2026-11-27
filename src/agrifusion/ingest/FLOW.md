# Layer0 Flow

## Purpose

`layer0` is the raw-ingestion lane: it reads data from the configured
source, decides whether the payload should be fetched and persisted, and
writes immutable evidence into `output/Layer0`.

## Entrypoint

- CLI:
  - `agrifusion --only-layer0 ...`
- Runtime:
  - `src/agrifusion/cli.py -> run_layer0()`
  - `src/agrifusion/ingest/pipeline.py -> Layer0IngestionPipeline.run()`

## Implemented flow

```mermaid
flowchart TD
    A["run_layer0()"] --> B["Build source adapter"]
    B --> C["Load previous sync_state"]
    C --> D["fetch_latest_meta_payload()"]
    D --> E["parse_latest_meta()"]
    E --> F["decide_sync()"]
    F --> G["build_sync_state()"]

    G --> H{"duplicate_source?"}
    H -- "No" --> I["Write latest_meta + source audit artifacts"]
    H -- "Yes" --> N["Skip latest_meta/audit writes"]

    I --> J{"should_fetch_current?"}
    N --> J
    J -- "Yes" --> K["fetch_latest_current_payload()"]
    K --> L["new_raw/latest.json (verbatim)"]
    L --> M["records/: put(kind=latest)"]
    J -- "No" --> O["No current payload fetch"]

    M --> P{"full_history?"}
    O --> P
    P -- "Yes" --> Q["fetch telemetry (verbatim)"]
    Q --> R["records/: put(kind=telemetry) per record, date window applied"]
    P -- "No" --> S["Skip backfill"]

    R --> T["records/index.json, sync_state.json, runs/<run_id>.json"]
    S --> T
    T --> U["Return Layer0IngestionResult"]
```

## What comes in

- CLI arguments from `src/agrifusion/cli.py`
- `.env` (repo root; legacy `Backend/.env` is still read) and runtime settings
- source adapter: Firebase RTDB or JSON export
- previous sync state: `Layer0/Firebase_data/new_raw/sync_state.json`

## What goes out

See [README.md section 2](README.md#2-on-disk-format-the-contract-with-canonical).
When `--full-history` is requested, telemetry is stored even if latest-meta
synchronization classifies the source as a duplicate; already stored records are
verified by hash and not written again.

## Folder map

- `pipeline.py`
  - main orchestration
- `sources/`
  - adapter-specific fetch/load logic
- `sync/`
  - parse latest meta, decide sync, build next sync state
- `stores/`
  - write latest/raw/history/sync-state artifacts
- `record_store.py`
  - raw record store format (writer + reader used by canonical)
- `utils/`
  - layout and low-level helpers

## Key logic boundaries

- `sources/` may know source APIs and file formats
- `sync/` may decide duplicate/new/retry behavior
- `stores/` may persist artifacts; the record format itself lives only in `record_store.py`
- nothing in ingest translates or normalizes records
- `pipeline.py` should orchestrate rather than accumulate large source
  or persistence rules

## Read this next

1. `pipeline.py`
2. `sources/firebase.py` or `sources/json_export.py`
3. `sync/latest_sync.py`
4. `stores/artifact_store.py`
5. `record_store.py`, `stores/telemetry_store.py`
6. `stores/sync_state_store.py`
