from __future__ import annotations

from pathlib import Path

import pandas as pd

from ..contracts import GROUP_PREFIXES


class DebugViewWriter:
    def __init__(self, output_root: Path):
        self.views_root = output_root.resolve() / "views"

    def ensure_directories(self) -> None:
        self.views_root.mkdir(parents=True, exist_ok=True)

    def write(self, canonical_df: pd.DataFrame) -> None:
        view_specs = {
            "sht_history.csv": GROUP_PREFIXES["sht"],
            "npk_history.csv": GROUP_PREFIXES["npk"],
            "record_time_history.csv": GROUP_PREFIXES["record_time"],
            "delivery_network_history.csv": GROUP_PREFIXES["delivery_network"],
            "device_system_history.csv": GROUP_PREFIXES["device_system"],
        }
        for filename, prefixes in view_specs.items():
            columns = [
                column
                for column in canonical_df.columns
                if any(column.startswith(prefix) for prefix in prefixes)
            ]
            if "record.id" not in columns and "record.id" in canonical_df.columns:
                columns = ["record.id", *columns]
            canonical_df.loc[:, columns].to_csv(self.views_root / filename, index=False)
