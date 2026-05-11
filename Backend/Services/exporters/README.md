# Exporters Pipeline

`Backend/Services/exporters` is the raw-source export package. It reads source data from Firebase RTDB, a local RTDB JSON export, or Open-Meteo, then writes canonical local artifacts under `Output_data/Layer0` for downstream Layer1 preprocessing.

## Main Flow

```text
ExportPipeline
    -> sources/
    -> sync/
    -> stores/
    -> Output_data/Layer0
```

The pipeline does four things:

- reads the latest metadata and current payload from a source adapter,
- decides whether the source contains new data or only a retry/duplicate state,
- writes reproducible local artifacts,
- saves sync state so the next run can compare against the previous run.

## Package Layout

```text
exporters/
|-- pipeline.py
|-- sources/
|   |-- base.py
|   |-- firebase.py
|   |-- json_export.py
|   `-- open_meteo.py
|-- stores/
|   |-- artifact_store.py
|   |-- sync_state_store.py
|   `-- telemetry_store.py
|-- sync/
|   `-- latest_sync.py
|-- models/
|   `-- telemetry.py
|-- utils/
|   |-- file_store.py
|   |-- json_ordering.py
|   `-- layout.py
`-- docs/
    `-- pipeline.md
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
- `open_meteo.py`: Open-Meteo fetcher with two separated stores:
  - `Meteo_forecast_ifs`: current IFS forecast stream for realtime inference.
  - `Meteo_archive_era5`: delayed ERA5 archive stream for backfill/training.

## Main CLI Commands

Layer0-only ingestion:

```powershell
python Backend\main.py --only-layer0 --source firebase --node-id Node1
python Backend\main.py --only-layer0 --source firebase --node-id Node1 --full-history
python Backend\main.py --only-layer0 --source firebase --node-id Node1 --start-date 2026-04-01 --end-date 2026-04-30
```

Date-window rules for Firebase/JSON history materialization:

- missing `--start-date` means from the first available record,
- missing `--end-date` means to the latest available data,
- date-window runs still sync latest metadata/current payload for state tracking,
- `--latest-only` disables backfill and cannot be combined with date windows.

## Open-Meteo Commands

```powershell
python Backend\main.py --only-layer0 --sync-meteo --meteo-mode forecast
python Backend\main.py --only-layer0 --sync-meteo --meteo-mode archive --meteo-archive-days 5
python Backend\main.py --only-layer0 --sync-meteo --meteo-mode all --meteo-start-date 2026-04-24 --meteo-end-date 2026-05-01
python Backend\main.py --only-layer1 --include-meteo-archive-layer1
```

By default, Layer1 preprocessing reads `Meteo_forecast_ifs`. ERA5 archive is only included when `--include-meteo-archive-layer1` is passed, so delayed archive data does not pollute the realtime path.

When a date range is provided, the CLI splits it by ERA5 availability:

```text
requested range: 2026-04-24 -> 2026-05-01
ERA5 archive:    2026-04-24 -> 2026-04-26
IFS forecast:    2026-04-27 -> 2026-05-01
```

The split point is `local_today - 5 days`, not `requested_end - 5 days`, so old backfill ranges still go fully through ERA5.

If the start date is omitted, Open-Meteo uses the configured default start date. If the end date is omitted, it syncs to local today. If no date range is provided, forecast sync uses the current IFS window and archive sync uses `--meteo-archive-days` unless `--full-history` is passed.

### `sync/`

Contains the sync decision logic.

- `parse_latest_meta()`: converts latest metadata payload into a typed snapshot.
- `decide_sync()`: returns statuses such as `new_data`, `source_refresh`, `retry_waiting`, `stale_after_retry`, or `duplicate_source`.
- `build_sync_state()`: creates the next persisted sync state.

### `stores/`

Writes local Layer0 artifacts.

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
