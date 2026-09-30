from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pandas as pd

from ..validation import normalize_column_names, require_columns


UCI_COLUMN_ROLES: dict[str, str] = {
    "CO(GT)": "criterion_only",
    "NMHC(GT)": "criterion_only",
    "C6H6(GT)": "criterion_only",
    "NOx(GT)": "criterion_only",
    "NO2(GT)": "criterion_only",
    "PT08.S1(CO)": "measurement",
    "PT08.S2(NMHC)": "measurement",
    "PT08.S3(NOx)": "measurement",
    "PT08.S4(NO2)": "measurement",
    "PT08.S5(O3)": "measurement",
    "T": "measurement",
    "RH": "measurement",
    "AH": "measurement",
}

UCI_COLUMN_MAP: dict[str, str] = {
    "CO(GT)": "criterion.co_gt_mg_m3",
    "NMHC(GT)": "criterion.nmhc_gt_ug_m3",
    "C6H6(GT)": "criterion.benzene_gt_ug_m3",
    "NOx(GT)": "criterion.nox_gt_ppb",
    "NO2(GT)": "criterion.no2_gt_ug_m3",
    "PT08.S1(CO)": "sensor.co",
    "PT08.S2(NMHC)": "sensor.nmhc",
    "PT08.S3(NOx)": "sensor.nox",
    "PT08.S4(NO2)": "sensor.no2",
    "PT08.S5(O3)": "sensor.o3",
    "T": "context.temperature_c",
    "RH": "context.relative_humidity_pct",
    "AH": "context.absolute_humidity",
}


def load_uci_raw(path: Path) -> tuple[pd.DataFrame, str]:
    if not path.is_file():
        raise FileNotFoundError(f"UCI source file is missing: {path}")
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            candidates = [name for name in archive.namelist() if name.lower().endswith("airqualityuci.csv")]
            if len(candidates) != 1:
                raise ValueError(f"Expected one AirQualityUCI.csv in {path}; found {candidates}")
            with archive.open(candidates[0]) as stream:
                payload = stream.read()
        frame = pd.read_csv(io.BytesIO(payload), sep=";", decimal=",")
        return normalize_column_names(frame), candidates[0]
    frame = pd.read_csv(path, sep=None, engine="python", decimal=",")
    frame = normalize_column_names(frame)
    return frame, path.name


def build_uci_candidate(raw_path: Path) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    raw, member_name = load_uci_raw(raw_path)
    raw = raw.loc[:, ~raw.columns.astype(str).str.startswith("Unnamed")].copy()
    raw["source_row_number"] = range(1, len(raw) + 1)
    timestamp = _parse_timestamp(raw)
    raw["timestamp"] = timestamp
    invalid_timestamp = raw["timestamp"].isna()
    empty_source_row = (
        raw["Date"].isna() & raw["Time"].isna()
        if {"Date", "Time"}.issubset(raw.columns)
        else pd.Series(False, index=raw.index)
    )
    exclusion_reason = pd.Series("INVALID_TIMESTAMP", index=raw.index, dtype="string")
    exclusion_reason.loc[empty_source_row] = "EMPTY_SOURCE_ROW"
    excluded = pd.DataFrame(
        {
            "source_row_number": raw.loc[invalid_timestamp, "source_row_number"],
            "exclusion_reason": exclusion_reason.loc[invalid_timestamp],
        }
    )
    valid = raw.loc[~invalid_timestamp].copy()
    required_sensor_columns = ["PT08.S1(CO)", "PT08.S3(NOx)"]
    require_columns(valid, ["timestamp", *required_sensor_columns], source_name="UCI Air Quality")
    required_criterion_columns = ["CO(GT)", "NOx(GT)"]
    missing_criterion_columns = [name for name in required_criterion_columns if name not in valid.columns]

    sentinel_counts = {
        column: int(pd.to_numeric(valid[column], errors="coerce").eq(-200).sum())
        for column in UCI_COLUMN_MAP
        if column in valid.columns
    }
    for column in UCI_COLUMN_MAP:
        if column in valid.columns:
            valid[column] = pd.to_numeric(valid[column], errors="coerce").replace(-200, pd.NA)

    candidate = pd.DataFrame(index=valid.index)
    candidate["sample_id"] = valid["source_row_number"].map(lambda row: f"uci_air_quality_360:row_{int(row):06d}")
    candidate["timestamp"] = valid["timestamp"]
    candidate["source_row_number"] = valid["source_row_number"]
    for source_name, canonical_name in UCI_COLUMN_MAP.items():
        candidate[canonical_name] = valid[source_name] if source_name in valid.columns else pd.NA
    sensor_features = [name for name, role in UCI_COLUMN_ROLES.items() if role == "measurement"]
    candidate = candidate.sort_values(["timestamp", "source_row_number"], kind="stable").reset_index(drop=True)
    candidate["audit.any_sensor_missing"] = candidate[[UCI_COLUMN_MAP[name] for name in sensor_features]].isna().any(axis=1).astype("boolean")
    candidate["audit.timestamp_delta_hours"] = candidate["timestamp"].diff().dt.total_seconds().div(3600)
    audit = {
        "dataset_id": "uci_air_quality_360",
        "raw_rows": int(len(raw)),
        "canonical_rows": int(len(candidate)),
        "invalid_timestamp_rows": int((invalid_timestamp & ~empty_source_row).sum()),
        "empty_source_rows": int((invalid_timestamp & empty_source_row).sum()),
        "missing_sentinel_counts": sentinel_counts,
        "member_name": member_name,
        "timestamp_time_basis": "local_wall_time_no_timezone_in_source",
        "missing_criterion_columns": missing_criterion_columns,
        "column_roles": {UCI_COLUMN_MAP[source]: role for source, role in UCI_COLUMN_ROLES.items()},
        "forbidden_model_columns": [
            UCI_COLUMN_MAP[name]
            for name, role in UCI_COLUMN_ROLES.items()
            if role == "criterion_only"
        ],
        "forbidden_source_columns": [name for name, role in UCI_COLUMN_ROLES.items() if role == "criterion_only"],
        "target_sensor_columns": {"co": "sensor.co", "nox": "sensor.nox"},
    }
    return candidate.convert_dtypes(), excluded.convert_dtypes(), audit


def _parse_timestamp(frame: pd.DataFrame) -> pd.Series:
    if "Date_Time" in frame:
        return pd.to_datetime(frame["Date_Time"], dayfirst=True, errors="coerce")
    require_columns(frame, ["Date", "Time"], source_name="UCI Air Quality")
    time = frame["Time"].astype("string").str.replace(".", ":", regex=False)
    return pd.to_datetime(frame["Date"].astype("string") + " " + time, dayfirst=True, errors="coerce")
