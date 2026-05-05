from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    from Backend.Config.path_manager import get_output_data_path
except ImportError:
    from ...Config.path_manager import get_output_data_path

from .anchors import build_era_features, fit_ec_model
from .loader import load_layer1_records, latest_in_window
from .model import (
    FuzzyMaterializationResult,
    MAX_METEO_STALE_SEC,
    MAX_NPK_STALE_SEC,
    MAX_SHT_STALE_SEC,
    StreamIndex,
)
from .qc import build_qc_features
from .rows import build_row
from .writer import write_outputs


def default_layer1_root() -> Path:
    try:
        from Backend.Config.path_manager import get_layer1_path
    except ImportError:
        from ...Config.path_manager import get_layer1_path
    return get_layer1_path()


def default_output_root() -> Path:
    return get_output_data_path() / "Layer2" / "fuzzy"


def materialize_layer2_fuzzy(
    layer1_root: Path,
    output_root: Path,
    limit: int | None = None,
) -> FuzzyMaterializationResult:
    stream_indexes = load_layer1_records(layer1_root)
    if not stream_indexes:
        raise FileNotFoundError(f"No Layer1 history.jsonl files found under {layer1_root}")

    sht_series: StreamIndex = stream_indexes.get("sht30", StreamIndex([], []))
    npk_series: StreamIndex = stream_indexes.get("npk", StreamIndex([], []))
    meteo_series: StreamIndex = stream_indexes.get("meteo", StreamIndex([], []))

    ec_slope, ec_intercept = fit_ec_model(npk_series.records)

    anchor_times = sorted(
        set(sht_series.ts_values)
        | set(npk_series.ts_values)
        | set(meteo_series.ts_values)
    )

    rows: list[dict[str, Any]] = []
    previous_state: dict[str, dict[str, float]] = {"_dt_hours": 0.0}
    previous_anchor_ts: int | None = None

    for anchor_ts in anchor_times:
        current_rows = {
            "sht30": latest_in_window(sht_series, anchor_ts, MAX_SHT_STALE_SEC),
            "npk": latest_in_window(npk_series, anchor_ts, MAX_NPK_STALE_SEC),
            "meteo": latest_in_window(meteo_series, anchor_ts, MAX_METEO_STALE_SEC),
        }
        if any(record is None for record in current_rows.values()):
            continue

        if previous_anchor_ts is None:
            dt_hours = 1.0
        else:
            dt_hours = max(1.0 / 60.0, (anchor_ts - previous_anchor_ts) / 3600.0)
        previous_state["_dt_hours"] = dt_hours

        era_features = build_era_features(meteo_series=meteo_series, anchor_ts=anchor_ts)
        qc_features = build_qc_features(
            current_rows=current_rows,
            anchor_ts=anchor_ts,
            ec_pred_slope=ec_slope,
            ec_pred_intercept=ec_intercept,
        )
        row = build_row(
            anchor_ts=anchor_ts,
            current_rows=current_rows,
            era_features=era_features,
            qc_features=qc_features,
            ec_pred_slope=ec_slope,
            ec_pred_intercept=ec_intercept,
            previous_state=previous_state,
        )
        rows.append(row)
        previous_anchor_ts = anchor_ts
        if limit is not None and len(rows) >= max(0, limit):
            break

    manifest = {
        "schema_version": 1,
        "pipeline": "layer2_fuzzy_materializer",
        "input_root": str(layer1_root),
        "output_root": str(output_root),
        "row_count": len(rows),
        "anchor_count": len(anchor_times),
        "ec_model": {
            "slope": ec_slope,
            "intercept": ec_intercept,
        },
        "artifacts": {
            "csv": str(output_root / "layer2_fuzzy.csv"),
        },
        "window_days": 5,
    }
    csv_path, manifest_path = write_outputs(rows=rows, output_root=output_root, manifest=manifest)

    return FuzzyMaterializationResult(
        input_root=layer1_root,
        output_root=output_root,
        csv_path=csv_path,
        manifest_path=manifest_path,
        row_count=len(rows),
        anchor_count=len(anchor_times),
    )

