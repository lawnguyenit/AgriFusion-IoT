from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from ...utils.storage import write_json
from ..contracts import (
    CATALOG_FIELDNAMES,
    Layer1BuildStats,
    catalog_entries,
)


class Layer1ReportWriter:
    def __init__(self, output_root: Path, views_root: Path):
        self.output_root = output_root.resolve()
        self.canonical_root = self.output_root / "canonical"
        self.quality_root = self.output_root / "quality_reports"
        self.views_root = views_root.resolve()

    def ensure_directories(self) -> None:
        self.canonical_root.mkdir(parents=True, exist_ok=True)
        self.quality_root.mkdir(parents=True, exist_ok=True)

    def write_feature_catalog(
        self,
        *,
        canonical_columns: Iterable[str],
        unknown_entries: list[dict[str, object]],
    ) -> Path:
        catalog_path = self.canonical_root / "feature_catalog.csv"
        entries = [*catalog_entries(), *unknown_entries]

        with catalog_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(CATALOG_FIELDNAMES))
            writer.writeheader()
            for entry in sorted(entries, key=lambda item: str(item["canonical_name"])):
                writer.writerow(entry)
        return catalog_path

    def write_missingness_reports(self, canonical_df: pd.DataFrame) -> tuple[Path, Path]:
        coverage_path = self.quality_root / "field_coverage.csv"
        missingness_path = self.quality_root / "missingness.csv"
        if canonical_df.empty:
            empty = pd.DataFrame(
                columns=["field", "non_null_count", "null_count", "coverage_ratio"]
            )
            empty.to_csv(coverage_path, index=False)
            empty.to_csv(missingness_path, index=False)
            return coverage_path, missingness_path

        rows = []
        total = len(canonical_df)
        for column in canonical_df.columns:
            non_null_count = int(canonical_df[column].notna().sum())
            null_count = total - non_null_count
            rows.append(
                {
                    "field": column,
                    "non_null_count": non_null_count,
                    "null_count": null_count,
                    "coverage_ratio": round(non_null_count / total, 6) if total else 0.0,
                }
            )
        report_df = pd.DataFrame(rows).sort_values("field").reset_index(drop=True)
        report_df.to_csv(coverage_path, index=False)
        report_df.to_csv(missingness_path, index=False)
        return coverage_path, missingness_path

    def write_variance_report(self, canonical_df: pd.DataFrame) -> Path:
        variance_path = self.quality_root / "field_variance.csv"
        rows: list[dict[str, Any]] = []
        for column in canonical_df.columns:
            series = canonical_df[column]
            numeric = pd.to_numeric(series, errors="coerce")
            non_null = int(series.notna().sum())
            row = {
                "field": column,
                "non_null_count": non_null,
                "distinct_count": int(series.dropna().nunique()),
                "numeric_variance": None,
                "is_constant_non_null": bool(
                    non_null > 0 and series.dropna().nunique() <= 1
                ),
            }
            if numeric.notna().any():
                variance = numeric.var(ddof=0)
                row["numeric_variance"] = None if pd.isna(variance) else float(variance)
            rows.append(row)
        pd.DataFrame(
            rows,
            columns=[
                "field",
                "non_null_count",
                "distinct_count",
                "numeric_variance",
                "is_constant_non_null",
            ],
        ).sort_values("field").to_csv(variance_path, index=False)
        return variance_path

    def write_duplicate_fields_report(
        self,
        *,
        unknown_entries: list[dict[str, object]],
    ) -> Path:
        duplicate_path = self.quality_root / "duplicate_fields.csv"
        entries = [*catalog_entries(), *unknown_entries]
        rows: list[dict[str, Any]] = []
        grouped: dict[str, list[str]] = {}
        for entry in entries:
            source_path = str(entry.get("source_path") or "")
            if not source_path:
                continue
            grouped.setdefault(source_path, []).append(str(entry["canonical_name"]))
        for source_path, canonical_names in grouped.items():
            if len(canonical_names) < 2:
                continue
            rows.append(
                {
                    "source_path": source_path,
                    "canonical_names": "|".join(sorted(canonical_names)),
                    "count": len(canonical_names),
                }
            )
        pd.DataFrame(
            rows,
            columns=["source_path", "canonical_names", "count"],
        ).to_csv(duplicate_path, index=False)
        return duplicate_path

    def write_processing_report(
        self,
        *,
        canonical_df: pd.DataFrame,
        stats: Layer1BuildStats,
        canonical_history_path: Path,
        canonical_latest_path: Path,
        excluded_records_path: Path,
        feature_catalog_path: Path,
        field_coverage_path: Path,
        field_variance_path: Path,
        duplicate_fields_path: Path,
        missingness_path: Path,
        canonical_format: str,
        unknown_entries: list[dict[str, object]],
        segment_summaries: list[dict[str, object]],
        buffer_reason_audit_path: Path,
        segment_manifest_path: Path,
    ) -> Path:
        processing_report_path = self.quality_root / "processing_report.json"
        field_status_counts: dict[str, int] = {}
        for entry in [*catalog_entries(), *unknown_entries]:
            field_status = str(entry["field_status"])
            field_status_counts[field_status] = (
                field_status_counts.get(field_status, 0) + 1
            )
        payload = {
            "input_record_count": stats.input_record_count,
            "demo_record_count": stats.demo_record_count,
            "excluded_record_count": stats.excluded_record_count,
            "canonical_record_count": stats.canonical_record_count,
            "duplicate_record_id_count": stats.duplicate_record_id_count,
            "timestamp_parse_error_count": stats.timestamp_parse_error_count,
            "sht_packet_missing_count": stats.sht_packet_missing_count,
            "npk_packet_missing_count": stats.npk_packet_missing_count,
            "sht_fault_count": stats.sht_fault_count,
            "npk_fault_count": stats.npk_fault_count,
            "buffered_replay_count": stats.buffered_replay_count,
            "fallback_count": stats.fallback_count,
            "reset_or_power_on_count": stats.reset_or_power_on_count,
            "segment_count": stats.segment_count,
            "buffer_reason_audit_row_count": stats.buffer_reason_audit_row_count,
            "field_count_by_status": field_status_counts,
            "canonical_format": canonical_format,
            "warnings": list(stats.warnings),
            "segments": segment_summaries,
            "output_paths": {
                "canonical_history": str(canonical_history_path),
                "canonical_latest": str(canonical_latest_path),
                "excluded_records": str(excluded_records_path),
                "feature_catalog": str(feature_catalog_path),
                "field_coverage": str(field_coverage_path),
                "field_variance": str(field_variance_path),
                "duplicate_fields": str(duplicate_fields_path),
                "missingness": str(missingness_path),
                "buffer_reason_audit": str(buffer_reason_audit_path),
                "segment_manifest": str(segment_manifest_path),
                "views_root": str(self.views_root),
            },
            "row_count_check": int(len(canonical_df)),
        }
        write_json(processing_report_path, payload)
        return processing_report_path
