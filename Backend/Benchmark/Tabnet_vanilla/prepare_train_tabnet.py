from __future__ import annotations

from config import settings

# import Benchmark.Tabnet_vanilla.prepare_utils as utils
# import Benchmark.Tabnet_vanilla.config.feature_schema as schema
# import Benchmark.Tabnet_vanilla.config.settings as config
# import Backend.Config.IO.io_csv as io_csv


import prepare_utils as utils
import config.feature_schema as schema
import config.settings as config
import Backend.Config.IO.io_csv as io_csv


# Nếu CSV đã có cột nhãn thật, điền tên cột vào đây.
# Ví dụ: TARGET_COL = "stress_flag"
TARGET_COL: str | None = None


# =========================
# MAIN
# =========================
def main() -> None:
    utils.ensure_dir(config.OUT_DIR)

    df = io_csv.load_csv(config.CSV_PATH)
    df = utils.add_time_features(df)
    df = utils.sort_by_time(df)

    train_df, valid_df, test_df = utils.split_by_time(
        df=df,
        train_ratio=config.TRAIN_RATIO,
        valid_ratio=config.VALID_RATIO,
        test_ratio=config.TEST_RATIO,
    )

    # xóa các cột trace nếu có
    cols_to_drop = [col for col in config.DROP_COLS_IF_EXIST if col in df.columns]
    if cols_to_drop:
        df = df.drop(columns=cols_to_drop)

    # xác định feature columns dựa trên schema và config
    feature_cols = schema.get_feature_columns(df)

    # tính fill values từ train_df để điền vào valid_df và test_df sau này, đảm bảo không bị data leakage
    fill_values = utils.compute_fill_values(train_df, feature_cols)

    # điền NaN
    train_df = utils.apply_fill_values(train_df, fill_values)
    valid_df = utils.apply_fill_values(valid_df, fill_values)
    test_df = utils.apply_fill_values(test_df, fill_values)

    # xây dựng feature view (chỉ giữ các cột feature_cols) cho train/valid/test
    X_train = schema.build_feature_view(train_df, feature_cols)
    X_valid = schema.build_feature_view(valid_df, feature_cols)
    X_test = schema.build_feature_view(test_df, feature_cols)

    full_dataset    = config.OUT_DIR/"origin_dataset"
    dataset         = config.OUT_DIR/"dataset"

    utils.save_dataframe(train_df, full_dataset / "train_full.csv")
    utils.save_dataframe(valid_df, full_dataset / "valid_full.csv")
    utils.save_dataframe(test_df, full_dataset / "test_full.csv")

    utils.save_dataframe(X_train, dataset / "X_train.csv")
    utils.save_dataframe(X_valid, dataset / "X_valid.csv")
    utils.save_dataframe(X_test, dataset / "X_test.csv")

    manifest = {
        "input_csv": str(settings.CSV_PATH),
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
        y_train = schema.build_target_view(train_df, TARGET_COL)
        y_valid = schema.build_target_view(valid_df, TARGET_COL)
        y_test = schema.build_target_view(test_df, TARGET_COL)

        assert y_train is not None and y_valid is not None and y_test is not None

        utils.save_series(y_train, config.OUT_DIR / "y_train.csv")
        utils.save_series(y_valid, config.OUT_DIR / "y_valid.csv")
        utils.save_series(y_test, config.OUT_DIR / "y_test.csv")

        manifest["target_available"] = True
    else:
        manifest["target_available"] = False
        manifest["note"] = (
            "Target column is not set yet. "
            "Only X_train/X_valid/X_test and full splits were exported."
        )

    utils.save_manifest(config.OUT_DIR / "manifest.json", manifest)

    print("Done.")
    print(f"Input CSV: {config.CSV_PATH}")
    print(f"Rows total: {len(df)}")
    print(f"Train/Valid/Test: {len(train_df)}/{len(valid_df)}/{len(test_df)}")
    print(f"Feature count: {len(feature_cols)}")
    print(f"Output dir: {config.OUT_DIR}")


if __name__ == "__main__":
    main()