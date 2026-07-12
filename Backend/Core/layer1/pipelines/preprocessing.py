from __future__ import annotations

from pathlib import Path

import pandas as pd

try:
    from Config.runtime import BACKEND_SETTINGS
except ModuleNotFoundError:
    from ....Config.runtime import BACKEND_SETTINGS

from ...utils.common import iso_utc_now
from ...utils.storage import write_json
from ..contracts import (
    Layer1BuildStats,
    Layer1Result,
    TemporalSettings,
    active_field_names,
)
from ..loaders import FirebaseSourceLoader
from ..processors.canonical_row import CanonicalRowBuilder
from ..processors.temporal import apply_temporal_features
from ..publishers import LegacyCompatibilityPublisher
from ..reports import Layer1ReportWriter
from ..validation import (
    validate_canonical_invariants,
    validate_unknown_catalog_fields,
)
from ..writers import CanonicalOutputWriter, DebugViewWriter


class PreprocessingPipeline:
    def __init__(
        self,
        base_dir: Path | None = None,
        output_root: Path | None = None,
        *,
        temporal_settings: TemporalSettings | None = None,
        export_debug_views: bool = True,
        unknown_catalog_field_policy: str = "warn",
    ):
        self.base_dir = (base_dir or BACKEND_SETTINGS.base_dir).resolve()
        self.output_root = (output_root or BACKEND_SETTINGS.layer1_root).resolve()
        self.canonical_root = self.output_root / "canonical"
        self.views_root = self.output_root / "views"
        self.excluded_root = self.output_root / "excluded"
        self.quality_root = self.output_root / "quality_reports"
        self.temporal = temporal_settings or TemporalSettings()
        self.export_debug_views = export_debug_views
        self.unknown_catalog_field_policy = unknown_catalog_field_policy

        self._source_loader = FirebaseSourceLoader(self.base_dir)
        self._row_builder = CanonicalRowBuilder()
        self._canonical_writer = CanonicalOutputWriter(self.output_root)
        self._view_writer = DebugViewWriter(self.output_root)
        self._report_writer = Layer1ReportWriter(self.output_root, self.views_root)
        self._legacy_publisher = LegacyCompatibilityPublisher(self.output_root)

    def run(self) -> Layer1Result:
        source_records = self._source_loader.load()
        stats = Layer1BuildStats(input_record_count=len(source_records))
        canonical_rows: list[dict[str, object]] = []
        excluded_rows: list[dict[str, object]] = []

        for source_record in source_records:
            row = self._row_builder.build(source_record)
            self._accumulate_source_stats(row, stats)
            if bool(row["record.is_demo"]):
                row["record.excluded_reason"] = "demo_or_synthetic_record"
                excluded_rows.append(row)
                stats.demo_record_count += 1
                stats.excluded_record_count += 1
                continue
            canonical_rows.append(row)

        stats.canonical_record_count = len(canonical_rows)
        canonical_df = pd.DataFrame(canonical_rows)
        if canonical_df.empty:
            canonical_df = pd.DataFrame(columns=active_field_names())
        canonical_df, duplicate_count = apply_temporal_features(canonical_df, self.temporal)
        stats.duplicate_record_id_count = duplicate_count
        excluded_df = pd.DataFrame(excluded_rows)

        unknown_entries = validate_unknown_catalog_fields(
            canonical_columns=canonical_df.columns,
            stats=stats,
            policy=self.unknown_catalog_field_policy,
        )
        validate_canonical_invariants(canonical_df=canonical_df, stats=stats)

        output_paths = self._write_outputs(
            canonical_df=canonical_df,
            excluded_df=excluded_df,
            stats=stats,
            unknown_entries=unknown_entries,
        )
        sensor_counts = self._build_sensor_counts(canonical_df)

        manifest_payload = {
            "schema_version": 2,
            "pipeline": "layer1_canonical_preprocessing",
            "ran_at_utc": iso_utc_now(),
            "processed_source_records": stats.input_record_count,
            "filtered_out_records": stats.excluded_record_count,
            "total_new_snapshots": stats.canonical_record_count,
            "targets": sensor_counts,
            "canonical_record_count": stats.canonical_record_count,
            "demo_record_count": stats.demo_record_count,
            "excluded_record_count": stats.excluded_record_count,
            "output_paths": {key: str(value) for key, value in output_paths.items()},
            "warnings": list(stats.warnings),
        }
        manifest_path = self.output_root / "manifest.json"
        write_json(manifest_path, manifest_payload)

        return Layer1Result(
            status="ok",
            processed_source_records=stats.input_record_count,
            filtered_out_records=stats.excluded_record_count,
            total_new_snapshots=stats.canonical_record_count,
            output_root=self.output_root,
            manifest_path=manifest_path,
            sensor_counts=sensor_counts,
            canonical_record_count=stats.canonical_record_count,
            excluded_record_count=stats.excluded_record_count,
            demo_record_count=stats.demo_record_count,
            canonical_history_path=output_paths["canonical_history_path"],
            canonical_latest_path=output_paths["canonical_latest_path"],
        )

    def _write_outputs(
        self,
        *,
        canonical_df: pd.DataFrame,
        excluded_df: pd.DataFrame,
        stats: Layer1BuildStats,
        unknown_entries: list[dict[str, object]],
    ) -> dict[str, Path]:
        self._canonical_writer.ensure_directories()
        self._report_writer.ensure_directories()
        if self.export_debug_views:
            self._view_writer.ensure_directories()

        canonical_history_path, canonical_format = self._canonical_writer.write_history(canonical_df)
        canonical_latest_path = self._canonical_writer.write_latest_snapshot(canonical_df)
        excluded_records_path = self._canonical_writer.write_excluded_records(excluded_df)
        feature_catalog_path = self._report_writer.write_feature_catalog(
            canonical_columns=canonical_df.columns,
            unknown_entries=unknown_entries,
        )
        field_coverage_path, missingness_path = self._report_writer.write_missingness_reports(canonical_df)
        field_variance_path = self._report_writer.write_variance_report(canonical_df)
        duplicate_fields_path = self._report_writer.write_duplicate_fields_report(
            unknown_entries=unknown_entries,
        )
        processing_report_path = self._report_writer.write_processing_report(
            canonical_df=canonical_df,
            stats=stats,
            canonical_history_path=canonical_history_path,
            canonical_latest_path=canonical_latest_path,
            excluded_records_path=excluded_records_path,
            feature_catalog_path=feature_catalog_path,
            field_coverage_path=field_coverage_path,
            field_variance_path=field_variance_path,
            duplicate_fields_path=duplicate_fields_path,
            missingness_path=missingness_path,
            canonical_format=canonical_format,
            unknown_entries=unknown_entries,
        )
        if self.export_debug_views:
            self._view_writer.write(canonical_df)
        self._legacy_publisher.publish(canonical_df)

        return {
            "canonical_history_path": canonical_history_path,
            "canonical_latest_path": canonical_latest_path,
            "excluded_records_path": excluded_records_path,
            "feature_catalog_path": feature_catalog_path,
            "field_coverage_path": field_coverage_path,
            "field_variance_path": field_variance_path,
            "duplicate_fields_path": duplicate_fields_path,
            "missingness_path": missingness_path,
            "processing_report_path": processing_report_path,
        }

    def _accumulate_source_stats(
        self,
        row: dict[str, object],
        stats: Layer1BuildStats,
    ) -> None:
        if row.get("record.ts_sample") is None:
            stats.timestamp_parse_error_count += 1
        if row.get("sht.packet_present") is False:
            stats.sht_packet_missing_count += 1
        if row.get("npk.packet_present") is False:
            stats.npk_packet_missing_count += 1
        if row.get("sht.fault") is True:
            stats.sht_fault_count += 1
        if row.get("npk.fault") is True:
            stats.npk_fault_count += 1
        if row.get("delivery.is_buffered_replay") is True:
            stats.buffered_replay_count += 1
        if row.get("delivery.fallback_used") is True:
            stats.fallback_count += 1
        if row.get("device.reset_or_power_on") is True:
            stats.reset_or_power_on_count += 1

    def _build_sensor_counts(self, canonical_df: pd.DataFrame) -> dict[str, int]:
        if canonical_df.empty:
            return {"canonical": 0, "sht30": 0, "npk": 0, "meteo": 0}
        return {
            "canonical": int(len(canonical_df)),
            "sht30": int(canonical_df["sht.packet_present"].fillna(False).astype(bool).sum()),
            "npk": int(canonical_df["npk.packet_present"].fillna(False).astype(bool).sum()),
            "meteo": 0,
        }
