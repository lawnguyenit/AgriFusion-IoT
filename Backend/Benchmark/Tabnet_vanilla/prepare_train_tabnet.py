from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import tabnet_vanilla_config as config

# =========================
# CONFIG
# =========================
CSV_PATH = Path(__file__).parent / "Input" / "fushion.csv"
OUT_DIR = CSV_PATH.parent / "Prepared"

if OUT_DIR.exists():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

TRAIN_RATIO = 0.70
VALID_RATIO = 0.15
TEST_RATIO = 0.15

# Nếu CSV đã có cột nhãn thật, điền tên cột vào đây.
# Ví dụ: TARGET_COL = "stress_flag"
TARGET_COL: str | None = None

# Nếu chưa có nhãn thật, giữ None.
# Script này vẫn chuẩn bị X_train/X_valid/X_test trước.


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"CSV not found: {path}")
    return pd.read_csv(path)


def validate_ratios(train_ratio: float, valid_ratio: float, test_ratio: float) -> None:
    total = train_ratio + valid_ratio + test_ratio
    if not np.isclose(total, 1.0):
        raise ValueError(f"Ratios must sum to 1.0, got {total}")


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


def get_feature_columns(df: pd.DataFrame) -> list[str]:
    feature_cols: list[str] = []

    # gán prefix để tránh trùng tên cột giữa các nguồn
    for col in config.BASE_FEATURE_COLS:
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


def sort_by_time(df: pd.DataFrame) -> pd.DataFrame:
    return df.sort_values("time_key").reset_index(drop=True)


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


# =========================
# MAIN
# =========================
def main() -> None:
    ensure_dir(OUT_DIR)

    df = load_csv(CSV_PATH)
    df = add_time_features(df)
    df = sort_by_time(df)

    # xóa các cột trace nếu có
    cols_to_drop = [col for col in config.DROP_COLS_IF_EXIST if col in df.columns]
    if cols_to_drop:
        df = df.drop(columns=cols_to_drop)

    feature_cols = get_feature_columns(df)

    train_df, valid_df, test_df = split_by_time(
        df=df,
        train_ratio=TRAIN_RATIO,
        valid_ratio=VALID_RATIO,
        test_ratio=TEST_RATIO,
    )

    fill_values = compute_fill_values(train_df, feature_cols)

    train_df = apply_fill_values(train_df, fill_values)
    valid_df = apply_fill_values(valid_df, fill_values)
    test_df = apply_fill_values(test_df, fill_values)

    X_train = build_feature_view(train_df, feature_cols)
    X_valid = build_feature_view(valid_df, feature_cols)
    X_test = build_feature_view(test_df, feature_cols)

    save_dataframe(train_df, OUT_DIR / "train_full.csv")
    save_dataframe(valid_df, OUT_DIR / "valid_full.csv")
    save_dataframe(test_df, OUT_DIR / "test_full.csv")

    save_dataframe(X_train, OUT_DIR / "X_train.csv")
    save_dataframe(X_valid, OUT_DIR / "X_valid.csv")
    save_dataframe(X_test, OUT_DIR / "X_test.csv")

    manifest = {
        "input_csv": str(CSV_PATH),
        "n_rows_total": int(len(df)),
        "n_rows_train": int(len(train_df)),
        "n_rows_valid": int(len(valid_df)),
        "n_rows_test": int(len(test_df)),
        "feature_count": int(len(feature_cols)),
        "feature_cols": feature_cols,
        "target_col": TARGET_COL,
        "fill_values": fill_values,
    }

    if TARGET_COL is not None:
        y_train = build_target_view(train_df, TARGET_COL)
        y_valid = build_target_view(valid_df, TARGET_COL)
        y_test = build_target_view(test_df, TARGET_COL)

        assert y_train is not None and y_valid is not None and y_test is not None

        save_series(y_train, OUT_DIR / "y_train.csv")
        save_series(y_valid, OUT_DIR / "y_valid.csv")
        save_series(y_test, OUT_DIR / "y_test.csv")

        manifest["target_available"] = True
    else:
        manifest["target_available"] = False
        manifest["note"] = (
            "Target column is not set yet. "
            "Only X_train/X_valid/X_test and full splits were exported."
        )

    save_manifest(OUT_DIR / "manifest.json", manifest)

    print("Done.")
    print(f"Input CSV: {CSV_PATH}")
    print(f"Rows total: {len(df)}")
    print(f"Train/Valid/Test: {len(train_df)}/{len(valid_df)}/{len(test_df)}")
    print(f"Feature count: {len(feature_cols)}")
    print(f"Output dir: {OUT_DIR}")


if __name__ == "__main__":
    main()