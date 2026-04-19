
import pandas as pd
# from Benchmark.Tabnet_vanilla.config import settings
from config import settings
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