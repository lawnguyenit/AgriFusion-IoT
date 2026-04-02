# Layer25

Layer 2.5 fuses Layer 2 agent outputs into a wide table for downstream modeling.

## Purpose

- Read `history.jsonl` outputs from Layer 2.
- Align snapshots by `ts_hour_bucket`.
- Flatten agent outputs into one row per aligned hour bucket.
- Export a wide table suitable for model-ready feature engineering and TabNet-style workflows.

## Output

Artifacts are written to:

- `Backend/Output_data/Layer2.5/super_table/super_table.jsonl`
- `Backend/Output_data/Layer2.5/super_table/super_table.csv`
- `Backend/Output_data/Layer2.5/super_table/latest.json`
- `Backend/Output_data/Layer2.5/super_table/manifest.json`

## Column Naming

Columns use the pattern:

`<stream>__<sensor_id>__<section>__<field>`

Examples:

- `npk__npk_7in1_1__perception__soil_temp_c`
- `sht30__sht30_1__signals__air_stress_score`
- `meteo__open_meteo_10_0853_105_8678__perception__precipitation_mm`

This keeps the fused table explicit and avoids collisions across agents.
