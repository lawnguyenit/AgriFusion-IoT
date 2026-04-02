# environmental_intelligence

Environmental preprocessing modules for weather and related external context streams.

## Files

- `meteorology_flux.py`: Layer 1 ingest for Open-Meteo archive data into local raw storage.
- `meteo_health.py`: health scoring for weather snapshots.
- `meteo_processor.py`: Layer 2 processor for weather snapshots.
- `climatology_heritage.py`: reserved for broader climatology logic.

## Storage Layout

Open-Meteo raw data is written to:

- `Backend/Output_data/Layer1/OpenMeteo_Data/Meteo_data/history`
- `Backend/Output_data/Layer1/OpenMeteo_Data/Meteo_data/new_raw`

Layer 2 weather output is written to:

- `Backend/Output_data/Layer2/meteo/<sensor_id>`

Layer 2.5 fused table then reads the Layer 2 weather output together with NPK and SHT30 outputs.

## Sync Modes

- Default mode: fetch from the latest saved checkpoint to the current day, then keep only new hour buckets.
- `--full-history`: backfill from `2026-03-16` to the current day.

## Timestamp Convention

- Raw weather records store both `ts_server` and `ts_hour_bucket`.
- `ts_hour_bucket` is the main alignment key for Layer 2 rolling windows and Layer 2.5 fusion.
