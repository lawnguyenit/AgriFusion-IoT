from __future__ import annotations

from collections.abc import Callable

import pandas as pd


def build_split_assignment_frame(
    *frames: pd.DataFrame,
    group_id_resolver: Callable[[str, dict[str, object]], object] | None = None,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    resolver = group_id_resolver or (lambda sample_id, _row: sample_id)
    for frame in frames:
        if frame.empty:
            continue
        for row in frame.to_dict(orient="records"):
            sample_id = str(row["sample_id"])
            effective_partition = str(row["effective_partition"])
            rows.append(
                {
                    "sample_id": sample_id,
                    "sample_type": row["sample_type"],
                    "task_id": row["task_id"],
                    "base_partition": row["base_partition"],
                    "effective_partition": effective_partition,
                    "eligibility_status": "eligible" if effective_partition != "excluded" else "excluded",
                    "exclusion_reason": row.get("exclusion_reason", pd.NA),
                    "group_id": resolver(sample_id, row),
                }
            )
    return pd.DataFrame(rows).convert_dtypes()
