from __future__ import annotations

import pandas as pd


def write_artifact_catalog(path, rows: list[dict[str, object]]) -> None:
    catalog_df = pd.DataFrame(rows).convert_dtypes()
    path.parent.mkdir(parents=True, exist_ok=True)
    catalog_df.to_csv(path, index=False)
