from __future__ import annotations

import hashlib
import json

import pandas as pd

from Backend.Benchmark.common.provenance import resolve_code_commit
from Backend.Benchmark.weak_labels.point import build_threshold_context
from Backend.Benchmark.weak_labels.shared.helpers import hash_dataframe_rows


def build_initial_source_threshold_context(
    continuity_df: pd.DataFrame,
    *,
    initial_train_start: pd.Timestamp,
    initial_train_end: pd.Timestamp,
) -> tuple[object, pd.DataFrame, dict[str, object]]:
    working = continuity_df.copy()
    working["base_partition"] = "excluded"
    mask = (
        (working["deployment_domain_name"].astype("string") == "P1_SOURCE")
        & (working["timestamp_local"] >= initial_train_start)
        & (working["timestamp_local"] < initial_train_end)
    )
    working.loc[mask, "base_partition"] = "train"
    threshold_context = build_threshold_context(working, threshold_mode="TRAIN_FITTED_GLOBAL")
    fit_rows = working.loc[
        mask & working["low_moisture_applicable"].fillna(False).astype(bool),
        ["record.id", "npk.soil_moisture_pct"],
    ].copy()
    moisture_values = pd.to_numeric(fit_rows["npk.soil_moisture_pct"], errors="coerce").dropna()
    sensitivity_df = pd.DataFrame(
        [
            {
                "threshold_id": "low_relative_moisture_quantiles_initial_p1",
                "policy": "FROZEN_INITIAL_SOURCE",
                "source_domain": "P1_SOURCE",
                "fit_start": initial_train_start.isoformat(),
                "fit_end": initial_train_end.isoformat(),
                "fit_record_count": int(len(moisture_values)),
                "q05": float(moisture_values.quantile(0.05)),
                "q10": float(moisture_values.quantile(0.10)),
                "q15": float(moisture_values.quantile(0.15)),
                "q20": float(moisture_values.quantile(0.20)),
            }
        ]
    ).convert_dtypes()
    manifest = {
        "threshold_id": "low_relative_moisture_q10_frozen_initial_source",
        "threshold_version": "2026-07-16.eval-protocol.v1",
        "policy": "FROZEN_INITIAL_SOURCE",
        "fold_id": "initial_p1_train",
        "source_domain": "P1_SOURCE",
        "fit_partition": "train",
        "fit_start": initial_train_start.isoformat(),
        "fit_end": initial_train_end.isoformat(),
        "fit_record_count": int(len(moisture_values)),
        "fit_record_hash": hash_dataframe_rows(fit_rows.astype("string")),
        "threshold_value": float(threshold_context.low_moisture_global.q10),
        "source_fields": ["npk.soil_moisture_pct"],
    }
    return threshold_context, sensitivity_df, manifest


def build_protocol_config_hash(config_dict: dict[str, object]) -> str:
    encoded = json.dumps(config_dict, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
