# Mock telemetry generator

## Purpose
`firebase_mock_sender.py` generates mock telemetry for `Node1` on a 15-minute wake cycle, with short retry bursts on failure, and can optionally upload to Firebase RTDB.

## Input
- `--start YYYY-MM-DD` or ISO datetime.
- `--days N` or `--end YYYY-MM-DD`.
- `--stop-before-layer0-start` to stop before the first date already present in `Backend/Output_data/Layer0/Firebase_data/history`.
- Timing controls:
  - `--seed`
  - `--device-jitter-min-sec`
  - `--device-jitter-max-sec`
  - `--server-delay-min-sec`
  - `--server-delay-max-sec`

## Output
- Telemetry writes under:
  - `/Node1/telemetry/YYYY-MM-DD/<ts>`
- Auxiliary writes for `info`, `live`, `latest`, and related snapshots.
- `--dry-run` can write a JSON bundle for inspection before upload.

## Run
```powershell
python D:\AgriFusion-IoT\IoT_Node\scripts\firebase_mock_sender.py --dry-run --start 2026-04-01 --days 27 --output-file D:\AgriFusion-IoT\IoT_Node\scripts\Temp\mock_sender.json
```

## Current assumptions
- Default sampling wake interval is 15 minutes.
- Irrigation is distributed around 6:30 -> 8:00, not fixed exactly at 7:00.
- `ts_server` is the upload timestamp, and is normally delayed from `ts_sample` by about 50 -> 116 seconds to match real telemetry.
- The generator now defaults to `--source-mode backup`, which replays empirical Layer1 values from `Backend/Output_data_bk/Output_data_bk/Layer1/{npk,sht30}/history.jsonl` by matching `event_key` across NPK and SHT30, then runs those rows through a stateful transform so the mock keeps the same plateaus, long holds, and event-driven jumps without copying the absolute values verbatim.
- `sample_time_reconstructed` is treated as a backfill-era flag before 2026-04-24, while post-cutover records are usually raw-style uploads with only a small number of replay/buffer cases.
- `SHT30 humidity` is saturated near `99.99%` at night, while daytime hours before 2026-04-24 now use broader per-day warps, phase shifts, and shock terms so adjacent days do not collapse into a near-copy template.
- Open-Meteo archive data under `Backend/Output_data/Layer0/OpenMeteo_Data/Meteo_archive_era5` is used as the daily meteo baseline for temperature and humidity correlation.
- The daytime humidity and temperature envelopes are not fixed across days; each day gets its own archive-backed floor/ceiling and curve warp so daily min/max values can move around. Pre-24/4 backfill days intentionally have wider variability than post-cutover live-style days.
- Nighttime humidity, watering windows, and rainy hours are forced to `99.99` to match the real behavior you observed.
- In backup replay mode, `EC` is no longer copied row-by-row. The script now follows the delta pattern from the backup sequence, holds values for long stretches, and only moves faster when the replayed source itself shows an event-strength jump. Integer `N + P + K` are recalculated from that transformed `EC` and then passed through a sticky integer channel so they mostly stay flat, drift by `1-2`, and only jump hard around replayed watering/rain-style regions.
- In backup replay mode, `pH` is treated as a slow, stable signal after the startup transient has been trimmed out. It stays in a stable 6.x -> 7.0 band and only moves by about `0.1` per sample, so the replay does not inherit unrealistic fast acid swings from the raw backup source.
- In backup replay mode, telemetry metadata is no longer marked as reconstructed for every pre-24/4 sample. The default behavior is now raw-style upload metadata, with only a very small number of reconstructed / buffered / fallback flags left in place to avoid an obviously synthetic all-false or all-true pattern.
- When the replay length is shorter than the requested mock timeline, the script trims the startup transient from the backup, rotates the replay loop to a stable region, and adds a small per-cycle drift so the output does not snap back to the original low-start sensor state at wrap boundaries.
- In generated mode, `EC` is driven by a humidity parabola baseline plus event-driven, stepwise transitions.
- If the original backup root is missing, backup replay will fall back to `Backend/Output_data copy/Layer1` automatically so the empirical replay mode still works after local folder reshuffles.
- In generated mode, `EC` remains tied to the soil-humidity-driven parabola and `N + P + K` still remain a direct function of `EC`.
- `pH` stays around 6.x, is quantized to 0.1 steps, and has a short abnormal low window around the late-April reconnect/recovery period.
- `packet` fields were trimmed to stay closer to the real schema.
- `sensors.*` mirrors `packet.*` validity and error state so packet-level QA and summary-level QA never disagree.
- `event_meta.duration_ms` and `npk_data.read_duration_ms` stay around the real 64 -> 67 ms range, and `sht30_data.sht_read_elapsed_ms` is fixed at 22 ms, matching the observed export.

## Risks / limits
- This is still a synthetic model derived from Layer0 behavior; it is not a replacement for real field telemetry.
- The pH anomaly is simulated with a fixed window in the generated timeline, so moving the start date also moves that anomaly window.
- A few failure records are still allowed so the output keeps the shape of real telemetry.
