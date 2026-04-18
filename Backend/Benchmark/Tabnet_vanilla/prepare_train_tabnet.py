from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

import Benchmark.Tabnet_vanilla.config.settings as settings
import Benchmark.Tabnet_vanilla.config.validate_config as validate
import Benchmark.Tabnet_vanilla.config.feature_schema as schema
import Benchmark.Tabnet_vanilla.config.splitters as splitters
import Benchmark.Tabnet_vanilla.config.time_features as time
import Benchmark.Tabnet_vanilla.config.exported as exported


# =========================
# CONFIG
# =========================
CSV_PATH = Path(__file__).parent / "Input" / "fushion.csv"
OUT_DIR = CSV_PATH.parent / "Prepared"

if OUT_DIR.exists():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

# Nếu CSV đã có cột nhãn thật, điền tên cột vào đây.
# Ví dụ: TARGET_COL = "stress_flag"
TARGET_COL: str | None = None


# =========================
# MAIN
# =========================
def main() -> None:
    validate.ensure_dir(OUT_DIR)

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