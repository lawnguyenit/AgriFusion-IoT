from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from Backend.Benchmark.shared.labels import load_event_label_frame


@dataclass(frozen=True)
class LegacyEventBridgeResult:
    enriched_canonical_df: pd.DataFrame
    coverage_report: dict[str, object]
    event_frame: pd.DataFrame


def bridge_legacy_event_labels(
    canonical_df: pd.DataFrame,
    *,
    event_csv_path: Path,
) -> LegacyEventBridgeResult:
    if not event_csv_path.exists():
        raise FileNotFoundError(f"Legacy benchmark event CSV not found: {event_csv_path}")
    if "record.ts_server" not in canonical_df.columns:
        raise ValueError("Canonical history is missing required column 'record.ts_server' for legacy event bridging.")

    event_frame = load_event_label_frame(event_csv_path)
    canonical = canonical_df.copy()
    canonical["_legacy_bridge_timestamp"] = pd.to_numeric(canonical["record.ts_server"], errors="coerce")
    if canonical["_legacy_bridge_timestamp"].isna().any():
        raise ValueError("Canonical history contains non-numeric 'record.ts_server' values.")
    canonical["_legacy_bridge_timestamp"] = canonical["_legacy_bridge_timestamp"].astype("int64")

    event_payload = event_frame.copy()
    event_payload["_legacy_bridge_timestamp"] = pd.to_numeric(event_payload["timestamp"], errors="coerce").astype("int64")
    bridge_columns = [column for column in event_payload.columns if column not in {"timestamp", "_legacy_bridge_timestamp"}]
    merged = canonical.merge(
        event_payload[["_legacy_bridge_timestamp", *bridge_columns]],
        on="_legacy_bridge_timestamp",
        how="left",
        sort=False,
        validate="one_to_one",
    )
    coverage_mask = merged["big_label"].notna() if "big_label" in merged.columns else pd.Series(False, index=merged.index)
    merged["legacy_event_coverage"] = coverage_mask.astype("boolean")
    merged["legacy_event_status"] = pd.Series(
        ["matched" if matched else "missing_legacy_alignment" for matched in coverage_mask.tolist()],
        dtype="string",
    )

    canonical_keys = set(canonical["_legacy_bridge_timestamp"].tolist())
    event_keys = set(event_payload["_legacy_bridge_timestamp"].tolist())
    coverage_report = {
        "event_csv_path": str(event_csv_path.resolve()),
        "canonical_row_count": int(len(canonical_df)),
        "legacy_event_row_count": int(len(event_frame)),
        "matched_row_count": int(coverage_mask.sum()),
        "unmatched_canonical_row_count": int((~coverage_mask).sum()),
        "unmatched_legacy_event_row_count": int(len(event_keys.difference(canonical_keys))),
        "canonical_key_column": "record.ts_server",
        "legacy_key_column": "timestamp",
    }
    merged = merged.drop(columns=["_legacy_bridge_timestamp"])
    return LegacyEventBridgeResult(
        enriched_canonical_df=merged,
        coverage_report=coverage_report,
        event_frame=event_frame,
    )
