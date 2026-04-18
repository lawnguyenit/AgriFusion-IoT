import numpy as np
import pandas as pd
from pathlib import Path
from Benchmark.Tabnet_vanilla.config import settings
import json

def validate_ratios(train_ratio: float, valid_ratio: float, test_ratio: float) -> None:
    total = train_ratio + valid_ratio + test_ratio
    if not np.isclose(total, 1.0):
        raise ValueError(f"Ratios must sum to 1.0, got {total}")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def split_by_time(
    df: pd.DataFrame,
    train_ratio: float,
    valid_ratio: float,
    test_ratio: float,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    validate_ratios(train_ratio, valid_ratio, test_ratio)

    n = len(df)
    if n < 10:
        raise ValueError(f"Dataset too small for split: n={n}")

    train_end = int(n * train_ratio)
    valid_end = train_end + int(n * valid_ratio)

    train_df = df.iloc[:train_end].copy()
    valid_df = df.iloc[train_end:valid_end].copy()
    test_df = df.iloc[valid_end:].copy()

    return train_df, valid_df, test_df

def compute_fill_values(train_df: pd.DataFrame, feature_cols: list[str]) -> dict[str, float]:
    fill_values: dict[str, float] = {}

    for col in feature_cols:
        series = train_df[col]

        # numeric only
        if pd.api.types.is_numeric_dtype(series):
            median_val = series.median()
            if pd.isna(median_val):
                median_val = 0.0
            fill_values[col] = float(median_val)

    return fill_values


def apply_fill_values(df: pd.DataFrame, fill_values: dict[str, float]) -> pd.DataFrame:
    out = df.copy()

    for col, val in fill_values.items():
        if col in out.columns:
            out[col] = out[col].fillna(val)

    return out

def add_time_features(df: pd.DataFrame) -> pd.DataFrame:
    if "time_key" not in df.columns:
        raise KeyError("Missing required column: time_key")

    out = df.copy()

    # time_key là unix timestamp theo giây
    dt_local = pd.to_datetime(out["time_key"], unit="s", utc=True).dt.tz_convert("Asia/Ho_Chi_Minh")

    out["hour_of_day"] = dt_local.dt.hour.astype(int)
    out["day_of_week"] = dt_local.dt.dayofweek.astype(int)

    # cyclic encoding cho giờ
    out["hour_sin"] = np.sin(2 * np.pi * out["hour_of_day"] / 24.0)
    out["hour_cos"] = np.cos(2 * np.pi * out["hour_of_day"] / 24.0)

    # có thể giữ để trace nhưng sẽ không đưa vào feature
    out["dt_local"] = dt_local.astype(str)

    return out

def sort_by_time(df: pd.DataFrame) -> pd.DataFrame:
    return df.sort_values("time_key").reset_index(drop=True)


def get_feature_columns(df: pd.DataFrame) -> list[str]:
    feature_cols: list[str] = []

    # gán prefix để tránh trùng tên cột giữa các nguồn
    for col in settings.BASE_FEATURE_COLS:
        if col in df.columns:
            feature_cols.append(col)

    # thêm time features nếu đã sinh
    for col in ["hour_of_day", "day_of_week", "hour_sin", "hour_cos"]:
        if col in df.columns:
            feature_cols.append(col)

    # Báo lỗi nếu không tìm thấy cột nào
    if not feature_cols:
        raise ValueError("No feature columns found in dataframe.")

    return feature_cols

def build_feature_view(df: pd.DataFrame, feature_cols: list[str]) -> pd.DataFrame:
    missing = [col for col in feature_cols if col not in df.columns]
    if missing:
        raise KeyError(f"Missing feature columns in dataframe: {missing}")

    return df[feature_cols].copy()


def build_target_view(df: pd.DataFrame, target_col: str | None) -> pd.Series | None:
    if target_col is None:
        return None

    if target_col not in df.columns:
        raise KeyError(f"Target column not found: {target_col}")

    return df[target_col].copy()

def save_dataframe(df: pd.DataFrame, path: Path) -> None:
    ensure_dir(path.parent)
    df.to_csv(path, index=False)


def save_series(series: pd.Series, path: Path) -> None:
    ensure_dir(path.parent)
    series.to_csv(path, index=False)


def save_manifest(path: Path, payload: dict[str, Any]) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")