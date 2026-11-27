from __future__ import annotations

import pandas as pd


DEPLOYMENT_DOMAIN_MAP: dict[str, str] = {
    "node1_seg_0001": "P1_SOURCE",
    "node1_seg_0002": "P2_TARGET",
}


def build_deployment_domain_frame(
    canonical_df: pd.DataFrame,
    *,
    segment_manifest: dict[str, object],
    mapping_version: str,
) -> pd.DataFrame:
    segment_rows = {
        str(item["segment_id"]): item
        for item in segment_manifest.get("segments", [])
        if isinstance(item, dict) and "segment_id" in item
    }
    rows: list[dict[str, object]] = []
    for row in canonical_df.loc[:, ["record.id", "record.ts_sample", "record.segment_id"]].itertuples(index=False):
        segment_id = str(row[2])
        segment_info = segment_rows.get(segment_id, {})
        rows.append(
            {
                "record_id": str(row[0]),
                "timestamp": int(row[1]),
                "layer1_segment_id": segment_id,
                "deployment_domain_id": DEPLOYMENT_DOMAIN_MAP.get(segment_id, "UNKNOWN"),
                "deployment_domain_name": DEPLOYMENT_DOMAIN_MAP.get(segment_id, "UNKNOWN"),
                "domain_start": segment_info.get("start_ts_sample"),
                "domain_end": segment_info.get("end_ts_sample"),
                "mapping_source": "layer1_segment_manifest",
                "mapping_version": mapping_version,
            }
        )
    return pd.DataFrame(rows).convert_dtypes()
