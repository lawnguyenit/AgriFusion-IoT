# Firebase RTDB ingestion server

Express service + CLI exporter to pull telemetry from Firebase Realtime Database and prepare data for ML pipelines.

## Setup

1. Copy `.env.example` to `.env`.
2. Fill `RTDB_URL` and `SERVICE_ACCOUNT_PATH`.
3. Install and run:

```powershell
npm install
npm start
```

## API endpoints

- `GET /health`
- `GET /data?path=/telemetry/raw&limit=100` (generic node reader)
- `GET /telemetry/raw?limit=5000&fromTs=<ms>&toTs=<ms>&includeRaw=1`
- `GET /telemetry/raw/latest`

`/telemetry/raw` returns normalized records with fields useful for model ingestion:
- `device_id`, `boot_id`, `seq`
- `event_ts_ms`, `ts_utc_ms`, `ts_device_ms`
- sensor reliability: `read_ok`, `error_code`, `retry_count`, `timeout_ms`, `read_duration_ms`, `crc_ok`, `frame_ok`
- risk flags: `consecutive_fail_count`, `recovered_after_fail`, `sensor_alarm`
- replay flags: `was_buffered`, `replayed`, `buffer_reason`

## Export data to file (server-side)

```powershell
npm run export:raw -- --limit 20000 --format jsonl
```

Examples:

```powershell
npm run export:raw -- --format csv --out .\exports\raw.csv
npm run export:raw -- --fromTs 1740672000000 --toTs 1740758400000 --format json
```

## Notes

- Keep service account credentials out of source control.
- For train pipelines, prefer `jsonl` export then process in Python/Node ETL.

