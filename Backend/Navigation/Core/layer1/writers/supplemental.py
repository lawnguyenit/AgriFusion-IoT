from __future__ import annotations

from pathlib import Path

import pandas as pd

from ...utils.common import iso_utc_now
from ...utils.storage import write_json
from .canonical import CanonicalOutputWriter
from .views import DebugViewWriter


class SupplementalOutputWriter:
    def __init__(self, output_root: Path):
        self.output_root = output_root.resolve()
        self.segments_root = self.output_root / "segments"
        self.quality_root = self.output_root / "quality_reports"

    def ensure_directories(self) -> None:
        self.segments_root.mkdir(parents=True, exist_ok=True)
        self.quality_root.mkdir(parents=True, exist_ok=True)

    def write_buffer_reason_audit(self, audit_df: pd.DataFrame) -> Path:
        audit_path = self.quality_root / "buffer_reason_audit.csv"
        columns = [
            "record.id",
            "record.segment_id",
            "record.node_id",
            "delivery.buffer_reason",
            "buffer_reason_raw",
        ]
        if audit_df.empty:
            pd.DataFrame(columns=columns).to_csv(audit_path, index=False)
            return audit_path
        audit_df.loc[:, columns].to_csv(audit_path, index=False)
        return audit_path

    def write_segment_outputs(
        self,
        *,
        canonical_df: pd.DataFrame,
        segment_summaries: list[dict[str, object]],
        export_debug_views: bool,
    ) -> Path:
        manifest_entries: list[dict[str, object]] = []
        for summary in segment_summaries:
            segment_id = str(summary["segment_id"])
            segment_root = self.segments_root / segment_id
            segment_df = canonical_df.loc[
                canonical_df["record.segment_id"] == segment_id
            ].reset_index(drop=True)

            canonical_writer = CanonicalOutputWriter(segment_root)
            canonical_writer.ensure_directories()
            history_path, canonical_format = canonical_writer.write_history(segment_df)
            latest_path = canonical_writer.write_latest_snapshot(segment_df)

            views_root = segment_root / "views"
            if export_debug_views:
                view_writer = DebugViewWriter(segment_root)
                view_writer.ensure_directories()
                view_writer.write(segment_df)

            manifest_entries.append(
                {
                    **summary,
                    "canonical_format": canonical_format,
                    "history_path": str(history_path),
                    "latest_path": str(latest_path),
                    "views_root": str(views_root),
                }
            )

        manifest_path = self.segments_root / "segments_manifest.json"
        write_json(
            manifest_path,
            {
                "schema_version": 1,
                "generated_at_utc": iso_utc_now(),
                "segment_count": len(manifest_entries),
                "segments": manifest_entries,
            },
        )
        return manifest_path
