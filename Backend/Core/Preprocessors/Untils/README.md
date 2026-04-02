# Untils

Shared utilities for preprocessing layers.

## Purpose

- `common.py`: shared numeric helpers, timestamp normalization, and rolling-window statistics.
- `storage.py`: shared JSON/JSONL file IO helpers.
- `pipeline.py`: Layer 2 preprocessing pipeline that reads Layer 1 raw data and writes Layer 2 agent outputs.

## Current Data Flow

- Layer 1 Firebase raw: `Backend/Output_data/Layer1/Firebase_data`
- Layer 1 Open-Meteo raw: `Backend/Output_data/Layer1/OpenMeteo_Data/Meteo_data`
- Layer 2 output: `Backend/Output_data/Layer2`
- Layer 2.5 fused output: `Backend/Output_data/Layer2.5`

## Timestamp Convention

- `ts_server`: original event timestamp.
- `ts_hour_bucket`: hour-aligned timestamp used for fusion and rolling windows.
- `observed_at_hour_local`: local ISO string for the aligned hour bucket.

The pipeline keeps `ts_server` for traceability and uses `ts_hour_bucket` for cross-agent alignment.
