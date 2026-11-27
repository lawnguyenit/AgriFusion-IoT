# ingest (Layer0)

## 1. What this layer guarantees

`src/agrifusion/ingest` copies source telemetry (Firebase RTDB or a JSON export of
the RTDB node) to local disk **without changing it**, and keeps sync state.

- **Verbatim.** Every record is stored as the JSON value received from the source:
  same keys, same values, same types. Nothing is renamed, defaulted, dropped or
  truncated (long firmware logs included). Ingest reads a few fields only to
  decide what is "latest" (timestamps, identity); it never rewrites a record.
- **Hashed and immutable.** A record file is named by the SHA-256 of its bytes and
  is never overwritten; a second version of the same event gets its own file.
  A changed file is detected (`RecordStoreError`).
- **Deterministic.** Record files and `records/index.json` contain no run
  timestamps: the same input gives byte-identical files, and ingesting the same
  input again changes nothing in `records/`.
- **Run metadata is separate.** Sync time, source descriptor, date filter and
  counts go to `runs/<run_id>.json` (one per run) and to the state files in
  `new_raw/`, never into record files.
- **No interpretation.** Translating firmware records into canonical rows is
  canonical's job (`agrifusion.canonical.adapters`). ingest never imports canonical.

## 2. On-disk format (the contract with canonical)

Owned by one module: [`record_store.py`](record_store.py) (stdlib only). ingest
writes through `RecordStoreWriter`; canonical reads only through
`RecordStoreReader` and `read_latest`. An architecture test enforces that
canonical imports nothing else from ingest.

```text
output/Layer0/Firebase_data/
|-- records/
|   |-- YYYY/MM/DD/<node_slug>_<event_key>_<sha256>.json   verbatim record
|   `-- index.json        date/event -> versions [{sha256, file, source_kind, source_path}]
|-- new_raw/
|   |-- latest.json        latest record, verbatim (same encoding)
|   |-- latest_meta.json   latest pointer (event/date/path, ts, record_sha256)
|   |-- sync_state.json    sync decision of the last run (has run times)
|   |-- source_manifest.json  source descriptor of the last run (has run times)
|   `-- source_snapshot.json  full source document (json-export / Firebase root mode)
`-- runs/<run_id>.json     one manifest per run
```

- Encoding: `json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + "\n"`,
  UTF-8. `sha256sum <file>` equals the hash in its name. Key order is sorted
  (JSON objects are unordered; values are unchanged).
- `source_kind`: `telemetry` (from `<node>/telemetry/<date>/<event>`) or `latest`
  (from `<node>/latest/current`). The firmware writes `latest/current` after the
  telemetry copy, so the two can differ (`sync.latest_updated`, upload timings);
  both are kept.
- Current version of an event (what canonical reads): the last `telemetry`
  version, else the last version of any kind.

## 3. Structure

```text
ingest/
|-- pipeline.py        orchestration (Layer0IngestionPipeline)
|-- record_store.py    on-disk format: writer + reader (contract with canonical)
|-- sources/           firebase.py, json_export.py, base.py (snapshot logic, read-only)
|-- stores/            telemetry_store.py (puts records), artifact/sync-state files
|-- sync/              latest_sync.py (parse latest meta, decide sync)
`-- utils/
```

## 4. Inputs

- Firebase RTDB (`<node>/latest/meta`, `<node>/latest/current`, `<node>/telemetry`)
  or the node root when `latest/meta` is absent
- JSON export of the node (`info`, `latest` (record or `{current, meta}`), `telemetry`)
- `.env` (repo root; legacy `Backend/.env` is still read), CLI parameters from `src/agrifusion/cli.py`

## 5. Usage

```powershell
agrifusion --only-layer0 --source firebase --node-id Node2                 # latest only
agrifusion --only-layer0 --source firebase --node-id Node2 --full-history  # whole telemetry
agrifusion --only-layer0 --source json-export --input-json C:\path\export.json --node-id Node2 --full-history
```

Without `--full-history` only the latest record is stored; repeated runs build up
`records/` from successive latest records.

## 6. Migration from the old layout

Before s4f, ingest wrote `history/` (records translated into a legacy packet
shape: lossy) and `raw_history/` (unread copy). Canonical no longer reads either.
Re-run ingest with `--full-history` to fill `records/` from the source; the old
folders are left untouched and can be deleted afterwards.

## 7. Detailed flow

See [FLOW.md](FLOW.md).
