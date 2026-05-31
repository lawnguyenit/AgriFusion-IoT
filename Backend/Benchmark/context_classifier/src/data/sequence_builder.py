from __future__ import annotations

import pandas as pd

from Backend.Benchmark.context_classifier.src.data.contracts import BASE_SENSOR_COLUMNS, PACKET_LOSS_FEATURE_COLUMNS


SEQUENCE_FEATURE_COLUMNS = BASE_SENSOR_COLUMNS + PACKET_LOSS_FEATURE_COLUMNS + ["record_present"]


def build_sequence_long(canonical_df: pd.DataFrame, lookback: int, stride: int) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    sequence_id = 0
    ordered = canonical_df.sort_values("timestamp").reset_index(drop=True)
    group_columns = ["data_origin", "source_reference"] if "source_reference" in ordered.columns else ["data_origin"]
    for _, group in ordered.groupby(group_columns, dropna=False, sort=False):
        current = group.reset_index(drop=True)
        for end_index in range(lookback - 1, len(current), stride):
            start_index = end_index - lookback + 1
            window = current.iloc[start_index : end_index + 1].reset_index(drop=True)
            target_label = str(window.iloc[-1]["context_label"])
            target_timestamp = int(window.iloc[-1]["timestamp"])
            sequence_origin = str(window["data_origin"].iloc[-1])
            split_name = str(window["split_name"].iloc[-1])
            sequence_id += 1
            for step_index, row in window.iterrows():
                payload: dict[str, object] = {
                    "sequence_id": sequence_id,
                    "step_index": int(step_index),
                    "target_timestamp": target_timestamp,
                    "target_label": target_label,
                    "sequence_origin": sequence_origin,
                    "split_name": split_name,
                    "timestamp": int(row["timestamp"]),
                    "data_origin": row["data_origin"],
                    "is_synthetic": int(row["is_synthetic"]),
                }
                for column in SEQUENCE_FEATURE_COLUMNS:
                    payload[column] = row[column]
                rows.append(payload)
    return pd.DataFrame(rows)
