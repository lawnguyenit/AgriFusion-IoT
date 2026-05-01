from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import pandas as pd
except ModuleNotFoundError as exc:
    raise ModuleNotFoundError(
        "Missing Python dependency 'pandas'. "
        "Activate ai_env and run: pip install -r Backend\\requirements.txt"
    ) from exc

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[2]))

try:
    from Services.config.settings import SETTINGS as EXPORT_SETTINGS
except ModuleNotFoundError:
    from ...Services.config.settings import SETTINGS as EXPORT_SETTINGS

TEXT_DROP_SUFFIXES = (
    "__source_path",
    "__source_event_key",
    "__sensor_type",
)
TEXT_DROP_COLUMNS = {
    "layer",
    "observed_at_hour_local",
    "sources_present",
    "missing_sources",
    "source_targets_expected",
}
KNOWN_CATEGORICAL_SUFFIXES = (
    "__context__transport",
    "__context__provider",
    "__context__timezone",
    "__context__soil_moisture_trend_24h",
    "__context__macro_humidity_trend_24h",
    "__context__temp_trend_window_key",
    "__derived__humidity_trend_24h",
    "__derived__soil_moisture_trend_24h",
    "__derived__temp_trend_24h",
    "__derived__temp_trend_short_horizon",
    "__derived__temp_trend_window_key",
)


@dataclass(frozen=True)
class TabNetBuildResult:
    status: str
    input_path: Path
    output_dir: Path
    matrix_csv_path: Path
    metadata_path: Path
    row_count: int
    feature_count: int
    numeric_feature_count: int
    categorical_feature_count: int
    dropped_column_count: int
    label_column: str | None


class TabNetSuperTableBuilder:
    def __init__(
        self,
        input_path: Path | None = None,
        output_dir: Path | None = None,
        label_column: str | None = None,
        max_categorical_cardinality: int = 32,
    ):
        self.input_path = input_path or (
            EXPORT_SETTINGS.layer25_root / "super_table" / "tabnet_ready.csv"
        )
        self.output_dir = output_dir or (EXPORT_SETTINGS.output_data_root / "TabNet")
        self.label_column = label_column
        self.max_categorical_cardinality = max_categorical_cardinality

    def run(self) -> TabNetBuildResult:
        if not self.input_path.exists():
            raise FileNotFoundError(f"Input super_table CSV not found: {self.input_path}")

        raw_df = pd.read_csv(self.input_path)
        if raw_df.empty:
            raise ValueError(f"Input super_table CSV is empty: {self.input_path}")

        working_df = raw_df.copy()
        working_df = self._add_time_features(working_df)

        label_series = None
        if self.label_column:
            if self.label_column not in working_df.columns:
                raise ValueError(
                    f"Label column '{self.label_column}' not found in {self.input_path}"
                )
            label_series = working_df[self.label_column].copy()

        dropped_columns = self._collect_drop_columns(working_df)
        feature_df = working_df.drop(columns=sorted(dropped_columns), errors="ignore")

        if self.label_column and self.label_column in feature_df.columns:
            feature_df = feature_df.drop(columns=[self.label_column])

        category_maps: dict[str, dict[str, int]] = {}
        numeric_fill_values: dict[str, float] = {}
        bool_columns: list[str] = []
        categorical_columns: list[str] = []
        numeric_columns: list[str] = []

        for column_name in list(feature_df.columns):
            series = feature_df[column_name]
            if self._is_bool_like(series):
                feature_df[column_name] = self._encode_bool_series(series)
                bool_columns.append(column_name)
                numeric_columns.append(column_name)
                continue

            numeric_series = pd.to_numeric(series, errors="coerce")
            if series.dtype.kind in {"i", "u", "f"} or numeric_series.notna().mean() >= 0.95:
                fill_value = self._resolve_numeric_fill_value(numeric_series)
                feature_df[column_name] = numeric_series.fillna(fill_value).astype(float)
                numeric_fill_values[column_name] = fill_value
                numeric_columns.append(column_name)
                continue

            if self._should_encode_categorical(column_name, series):
                encoded_series, mapping = self._encode_categorical_series(series)
                feature_df[column_name] = encoded_series
                category_maps[column_name] = mapping
                categorical_columns.append(column_name)
                continue

            feature_df = feature_df.drop(columns=[column_name])
            dropped_columns.add(column_name)

        if feature_df.empty:
            raise ValueError("No usable feature columns remain after TabNet cleaning")

        feature_df["ts_hour_bucket"] = pd.to_numeric(
            working_df["ts_hour_bucket"],
            errors="coerce",
        ).fillna(0).astype("int64")
        ordered_columns = ["ts_hour_bucket"] + [
            column_name
            for column_name in feature_df.columns
            if column_name != "ts_hour_bucket"
        ]
        feature_df = feature_df[ordered_columns]

        if label_series is not None:
            feature_df["label"] = self._encode_label_series(label_series)

        self.output_dir.mkdir(parents=True, exist_ok=True)
        matrix_csv_path = self.output_dir / "tabnet_matrix.csv"
        metadata_path = self.output_dir / "tabnet_schema.json"

        feature_df.to_csv(matrix_csv_path, index=False, encoding="utf-8")
        metadata_payload = {
            "schema_version": 1,
            "input_path": str(self.input_path),
            "output_matrix_path": str(matrix_csv_path),
            "row_count": int(len(feature_df)),
            "feature_count": int(
                len(feature_df.columns) - (1 if "label" in feature_df.columns else 0)
            ),
            "label_column": self.label_column,
            "id_column": "ts_hour_bucket",
            "bool_columns": sorted(bool_columns),
            "numeric_columns": sorted(set(numeric_columns + ["ts_hour_bucket"])),
            "categorical_columns": sorted(categorical_columns),
            "category_maps": category_maps,
            "numeric_fill_values": numeric_fill_values,
            "dropped_columns": sorted(dropped_columns),
        }
        metadata_path.write_text(
            json.dumps(metadata_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        return TabNetBuildResult(
            status="ok",
            input_path=self.input_path,
            output_dir=self.output_dir,
            matrix_csv_path=matrix_csv_path,
            metadata_path=metadata_path,
            row_count=int(len(feature_df)),
            feature_count=int(
                len(feature_df.columns) - (1 if "label" in feature_df.columns else 0)
            ),
            numeric_feature_count=len(set(numeric_columns + ["ts_hour_bucket"])),
            categorical_feature_count=len(categorical_columns),
            dropped_column_count=len(dropped_columns),
            label_column=self.label_column,
        )

    def _collect_drop_columns(self, df: pd.DataFrame) -> set[str]:
        dropped_columns = set(TEXT_DROP_COLUMNS)
        for column_name in df.columns:
            if column_name == self.label_column:
                continue
            if any(column_name.endswith(suffix) for suffix in TEXT_DROP_SUFFIXES):
                dropped_columns.add(column_name)
        return dropped_columns

    def _add_time_features(self, df: pd.DataFrame) -> pd.DataFrame:
        if "ts_hour_bucket" not in df.columns:
            raise ValueError("super_table input must contain ts_hour_bucket")

        out_df = df.copy()
        ts_series = pd.to_numeric(out_df["ts_hour_bucket"], errors="coerce").fillna(0).astype("int64")
        dt_series = pd.to_datetime(ts_series, unit="s", utc=True).dt.tz_convert(
            EXPORT_SETTINGS.timezone_name
        )
        hour_value = dt_series.dt.hour.astype(float)
        dayofyear_value = dt_series.dt.dayofyear.astype(float)

        out_df["time__hour_sin"] = hour_value.map(lambda value: math.sin(2.0 * math.pi * value / 24.0))
        out_df["time__hour_cos"] = hour_value.map(lambda value: math.cos(2.0 * math.pi * value / 24.0))
        out_df["time__dayofyear_sin"] = dayofyear_value.map(
            lambda value: math.sin(2.0 * math.pi * value / 366.0)
        )
        out_df["time__dayofyear_cos"] = dayofyear_value.map(
            lambda value: math.cos(2.0 * math.pi * value / 366.0)
        )
        return out_df

    def _is_bool_like(self, series: pd.Series) -> bool:
        non_null_values = {
            str(value).strip().lower()
            for value in series.dropna().unique().tolist()
            if str(value).strip() != ""
        }
        return bool(non_null_values) and non_null_values.issubset({"true", "false", "0", "1"})

    def _encode_bool_series(self, series: pd.Series) -> pd.Series:
        normalized = series.fillna(False).astype(str).str.strip().str.lower()
        return normalized.map({"true": 1, "1": 1, "false": 0, "0": 0}).fillna(0).astype(int)

    def _should_encode_categorical(self, column_name: str, series: pd.Series) -> bool:
        if any(column_name.endswith(suffix) for suffix in KNOWN_CATEGORICAL_SUFFIXES):
            return True
        non_null_unique = int(series.dropna().astype(str).str.strip().nunique())
        return 0 < non_null_unique <= self.max_categorical_cardinality

    def _encode_categorical_series(self, series: pd.Series) -> tuple[pd.Series, dict[str, int]]:
        normalized = series.fillna("__missing__").astype(str).str.strip()
        categories = ["__missing__"] + sorted(
            value for value in normalized.unique().tolist() if value != "__missing__"
        )
        mapping = {category: index for index, category in enumerate(categories)}
        return normalized.map(mapping).fillna(0).astype(int), mapping

    def _resolve_numeric_fill_value(self, numeric_series: pd.Series) -> float:
        valid_values = numeric_series.dropna()
        if valid_values.empty:
            return 0.0
        return float(valid_values.median())

    def _encode_label_series(self, label_series: pd.Series) -> pd.Series:
        if self._is_bool_like(label_series):
            return self._encode_bool_series(label_series)
        numeric_series = pd.to_numeric(label_series, errors="coerce")
        if numeric_series.notna().mean() >= 0.95:
            return numeric_series.fillna(self._resolve_numeric_fill_value(numeric_series))
        encoded_series, _ = self._encode_categorical_series(label_series)
        return encoded_series


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert Layer2.5 super_table/tabnet_ready.csv into a TabNet-friendly matrix."
    )
    parser.add_argument("--input-csv", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--label-column", type=str, default=None)
    parser.add_argument("--max-categorical-cardinality", type=int, default=32)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = TabNetSuperTableBuilder(
        input_path=args.input_csv,
        output_dir=args.output_dir,
        label_column=args.label_column,
        max_categorical_cardinality=args.max_categorical_cardinality,
    ).run()

    print(f"TabNet build status: {result.status}")
    print(f"Input: {result.input_path}")
    print(f"Rows: {result.row_count}")
    print(f"Features: {result.feature_count}")
    print(f"Numeric features: {result.numeric_feature_count}")
    print(f"Categorical features: {result.categorical_feature_count}")
    print(f"Dropped columns: {result.dropped_column_count}")
    print(f"Label column: {result.label_column}")
    print(f"Matrix CSV: {result.matrix_csv_path}")
    print(f"Metadata: {result.metadata_path}")


if __name__ == "__main__":
    main()
