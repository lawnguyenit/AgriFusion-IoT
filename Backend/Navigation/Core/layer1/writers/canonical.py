from __future__ import annotations

from pathlib import Path

import pandas as pd

from ...utils.storage import write_json
from ..processors.common import nest_row_by_namespace


class CanonicalOutputWriter:
    def __init__(self, output_root: Path):
        self.output_root = output_root.resolve()
        self.canonical_root = self.output_root / "canonical"
        self.excluded_root = self.output_root / "excluded"

    def ensure_directories(self) -> None:
        self.canonical_root.mkdir(parents=True, exist_ok=True)
        self.excluded_root.mkdir(parents=True, exist_ok=True)

    def write_history(self, canonical_df: pd.DataFrame) -> tuple[Path, str]:
        """Always write parquet (pyarrow is a required dependency; no CSV fallback)."""
        canonical_history_path = self.canonical_root / "telemetry_history.parquet"
        canonical_df.to_parquet(canonical_history_path, engine="pyarrow", index=False)
        return canonical_history_path, "parquet:pyarrow"

    def write_latest_snapshot(self, canonical_df: pd.DataFrame) -> Path:
        latest_path = self.canonical_root / "telemetry_latest.json"
        if canonical_df.empty:
            write_json(
                latest_path,
                {
                    "record": {},
                    "sht": {},
                    "npk": {},
                    "delivery": {},
                    "network": {},
                    "device": {},
                    "sensor": {},
                },
            )
            return latest_path

        ordered = canonical_df.copy()
        ordered["_ts_sort"] = pd.to_numeric(
            ordered["record.ts_sample"],
            errors="coerce",
        ).fillna(pd.to_numeric(ordered["record.ts_server"], errors="coerce"))
        ordered = ordered.sort_values(
            ["_ts_sort", "record.event_key"],
            kind="stable",
            na_position="last",
        )
        latest_row = ordered.iloc[-1].drop(labels=["_ts_sort"]).to_dict()
        write_json(latest_path, nest_row_by_namespace(latest_row))
        return latest_path

    def write_excluded_records(self, excluded_df: pd.DataFrame) -> Path:
        excluded_path = self.excluded_root / "excluded_records.csv"
        if excluded_df.empty:
            pd.DataFrame(
                columns=[
                    "record.id",
                    "record.date_key",
                    "record.event_key",
                    "record.excluded_reason",
                ]
            ).to_csv(excluded_path, index=False)
            return excluded_path
        excluded_df.to_csv(excluded_path, index=False)
        return excluded_path
