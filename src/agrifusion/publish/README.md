# agrifusion.publish

Publishes canonical Layer1 output to the dashboard contract `result/*`
(`docs/contracts/result.md`; machine-readable: `docs/contracts/result.schema.json`).

```text
agrifusion publish [--dry-run | --apply] [--input FILE] [--out FILE] [--node-id ID]
                   [--remote-diff] [--heartbeat] [--result-path result]
```

- Default is `--dry-run`: prints the planned multi-path update as JSON, writes nothing, needs no network.
  `--remote-diff` (implied by `--apply`) reads RTDB `result/` first and plans only the difference.
- `--out FILE` writes the planned final tree (useful for demo mode and tests).
- `--apply` does one `update()` (meta + latest + new history children + deletions of trimmed children).

## Mapping rules

- Input: `output/Layer1/canonical/telemetry_history.parquet`, read with `agrifusion.io.read_table`.
- `ts` = `record.ts_sample` (epoch seconds); history key = `String(ts)`. Same ts -> last row by `record.id` wins.
- Rows with `record.is_demo` true or non-empty `record.excluded_reason` are skipped.
- A value key is omitted (never null/0) when it is NaN/missing, outside the contract range, or its validity flag is
  explicitly `false`. A flag that is null/unknown does NOT drop the value (the golden data has null flags for
  ph/ec/proxy). Flags: air `sht.value_valid` (whole record); soil `npk.soil_temp_valid`, `npk.soil_moisture_valid`,
  `npk.ph_valid`, `npk.ec_valid`; npk `npk.{n,p,k}_proxy_valid`. All come from `result.schema.json`.
- A record without any value field is not published. `meta.node_id` = `--node-id` or `record.node_id` of the newest
  published row (no default node).
- Retention: drop `ts < newest - 7 days`, then keep the newest 800 per group. Remote records inside retention but
  absent from canonical are kept (canonical wins on equal ts).
- Idempotent: keys derive from `ts`; a re-run with the same data yields an empty update. `meta.published_ts` alone
  never triggers a write unless `--heartbeat` is given (so the dashboard's "stale" warning reflects data age).
- The planned tree is validated against the contract before anything is written.

## Boundaries

Imports `io`, `settings`, `cloud`. Only `agrifusion.cli` imports this package. The RTDB client
(`cloud.FirebaseRTDBClient`) gets `read()` (strict) and `update()`; `firebase_admin` is imported lazily.
