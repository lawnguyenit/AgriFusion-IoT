# Backend Data Pipelines

Python pipeline for AgriFusion data layers:

- Layer0 raw ingestion from Firebase RTDB, a local RTDB JSON export, and optionally Open-Meteo.
- Layer1 preprocessing from local Layer0 artifacts into structured per-stream snapshots.
- Layer2.5 fusion from Layer1 snapshots into a flat super-table for ML/research.

## Setup

1. Create a virtual environment.
2. Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

3. Copy `Services/.env.example` to `Services/.env`.
4. Fill Firebase credentials if you use `--source firebase`.
5. Set stable defaults in `Services/.env` or pass run-specific values on the CLI.

## Main CLI

`main.py` can run one layer independently or run from Layer0 through a target layer.

### Run One Layer Only

```powershell
python main.py --only-layer0 --source firebase --node-id Node1
python main.py --only-layer1
python main.py --only-layer2.5
```

### Run To A Target Layer

```powershell
python main.py --to-layer layer0 --source firebase --node-id Node1
python main.py --to-layer layer1 --source firebase --node-id Node1
python main.py --to-layer layer2.5 --source firebase --node-id Node1
```

Without `--to-layer` or `--only-*`, the default path is Layer0 -> Layer1 -> Layer2.5.

Legacy flags are still accepted:

```powershell
python main.py --layer2-only --skip-layer25
python main.py --skip-layer2
python main.py --skip-layer25
```

## Layer0 Sources

### Firebase

```powershell
python main.py --only-layer0 --source firebase --node-id Node1
```

Required env values:

- `DATABASE_URL`
- `FIREBASE_KEY_PATH`

By default, Firebase ingestion syncs the latest payload and appends the latest history snapshot when it is new. Use `--full-history` to materialize the full RTDB telemetry tree locally.

### JSON Export

Use this for offline debugging, fixture creation, or recovery when direct RTDB access is unavailable.

```powershell
python main.py --only-layer0 --source json-export `
  --input-json C:\path\to\agri-fusion-iot-default-rtdb-Node1-export.json `
  --node-id Node1 `
  --node-slug node1 `
  --npk-sensor-id npk_7in1_1 `
  --npk-sensor-type npk7in1 `
  --sht30-sensor-id sht30_1 `
  --sht30-sensor-type sht30_air `
  --full-history
```

The JSON export source expects:

- top-level `info`
- top-level `live`
- top-level `status_events`
- top-level `telemetry`

When packet metadata such as `sensor_id` or `sensor_type` is missing, the importer injects it from CLI or env configuration.

### Open-Meteo

Open-Meteo sync is opt-in and writes separate Layer0 stores for IFS forecast and ERA5 archive.

```powershell
python main.py --only-layer0 --sync-meteo --meteo-mode all
python main.py --only-layer0 --sync-meteo --meteo-mode forecast
python main.py --only-layer0 --sync-meteo --meteo-mode archive --meteo-archive-days 5
```

## Date Windows

Use `--start-date` and `--end-date` for a generic backfill window. Dates use `YYYY-MM-DD`.

```powershell
python main.py --to-layer layer1 --source firebase --node-id Node1 `
  --start-date 2026-04-01 --end-date 2026-04-30
```

Rules:

- Missing `--start-date` means from the first available record.
- Missing `--end-date` means to the latest available data.
- If both dates are provided in reverse order, the CLI swaps them.
- A date window implies Firebase/JSON history materialization for matching dates.

For Open-Meteo-specific windows, use:

```powershell
python main.py --only-layer0 --sync-meteo --meteo-mode all `
  --meteo-start-date 2026-04-24 --meteo-end-date 2026-05-01
```

If only `--meteo-end-date` is provided, ERA5 starts from the configured default start date. If only `--meteo-start-date` is provided, sync runs to local today. The CLI splits the date window by ERA5 availability:

```text
ERA5 archive: dates up to local_today - 5 days
IFS forecast: dates after local_today - 5 days
```

## Latest-Only Runs

Use `--latest-only` when you want the command shape to explicitly mean "no backfill".

```powershell
python main.py --to-layer layer1 --latest-only --source firebase --node-id Node1
python main.py --to-layer layer2.5 --latest-only --source firebase --node-id Node1
```

`--latest-only` cannot be combined with date windows or `--full-history`.

## Output Contract

Layer0 writes raw local artifacts:

- `Output_data/Layer0/Firebase_data/new_raw/latest.json`
- `Output_data/Layer0/Firebase_data/new_raw/latest_meta.json`
- `Output_data/Layer0/Firebase_data/new_raw/sync_state.json`
- `Output_data/Layer0/Firebase_data/new_raw/source_manifest.json`
- `Output_data/Layer0/Firebase_data/new_raw/source_snapshot.json`
- `Output_data/Layer0/Firebase_data/history/...`
- `Output_data/Layer0/OpenMeteo_Data/Meteo_forecast_ifs/...`
- `Output_data/Layer0/OpenMeteo_Data/Meteo_archive_era5/...`

Layer1 reads Layer0 artifacts and writes:

- `Output_data/Layer1/<stream>/history.jsonl`
- `Output_data/Layer1/<stream>/latest.json`
- `Output_data/Layer1/<stream>/state.json`
- `Output_data/Layer1/manifest.json`

Layer2.5 reads Layer1 artifacts and writes:

- `Output_data/Layer2.5/super_table/super_table.jsonl`
- `Output_data/Layer2.5/super_table/super_table.csv`
- `Output_data/Layer2.5/super_table/latest.json`
- `Output_data/Layer2.5/super_table/manifest.json`

## Assumptions And Limits

- Layer1 and Layer2.5 are incremental based on their local state/history files.
- Date filtering for Firebase/JSON applies when history is materialized; latest metadata/current payload is still synced for state tracking.
- Open-Meteo ERA5 has a delay window, so recent dates are routed to IFS forecast instead.
- The CLI does not delete old raw data, old processed snapshots, logs, datasets, or experiment results.

## Tests

Small non-writing checks:

```powershell
python -m py_compile Backend\main.py Backend\Services\exporters\pipeline.py Backend\Services\exporters\stores\telemetry_store.py
python Backend\main.py --help
```

Full pipeline commands may pull remote data and write output artifacts, so run them intentionally.
