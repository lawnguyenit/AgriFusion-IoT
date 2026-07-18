from __future__ import annotations

import pandas as pd


def enrich_point_continuity_features(continuity_df: pd.DataFrame) -> pd.DataFrame:
    ordered = continuity_df.copy()
    ordered["record.ts_sample"] = pd.to_numeric(ordered["record.ts_sample"], errors="coerce").astype("int64")
    ordered = ordered.sort_values(
        ["record.node_id", "record.ts_sample", "record.id"],
        kind="stable",
    ).reset_index(drop=True)

    previous_moisture: dict[str, float] = {}
    previous_ec: dict[str, float] = {}
    previous_low_run: dict[str, int] = {}
    moisture_rise_deltas: list[object] = []
    ec_shift_deltas: list[object] = []
    low_run_lengths: list[int] = []

    for _, row in ordered.iterrows():
        chunk_id = str(row.get("record.continuity_chunk_id", ""))
        moisture_value = pd.to_numeric(pd.Series([row.get("npk.soil_moisture_pct")]), errors="coerce").iloc[0]
        ec_value = pd.to_numeric(pd.Series([row.get("npk.ec")]), errors="coerce").iloc[0]

        previous_moisture_value = previous_moisture.get(chunk_id)
        previous_ec_value = previous_ec.get(chunk_id)
        moisture_rise_deltas.append(
            pd.NA if pd.isna(moisture_value) or previous_moisture_value is None else float(moisture_value) - previous_moisture_value
        )
        ec_shift_deltas.append(
            pd.NA if pd.isna(ec_value) or previous_ec_value is None else abs(float(ec_value) - previous_ec_value)
        )
        low_run_lengths.append(previous_low_run.get(chunk_id, 0))

        if pd.notna(moisture_value):
            previous_moisture[chunk_id] = float(moisture_value)
        if pd.notna(ec_value):
            previous_ec[chunk_id] = float(ec_value)

    ordered["moisture_rise_delta"] = pd.Series(moisture_rise_deltas, dtype="Float64")
    ordered["ec_shift_delta_abs"] = pd.Series(ec_shift_deltas, dtype="Float64")
    ordered["previous_low_run_length"] = pd.Series(low_run_lengths, dtype="Int64")
    return ordered
