from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from Backend.Core import Layer25FusionPipeline, PreprocessingPipeline
    from Config.runtime import BackendSettings
    from Services.clients import FirebaseRTDBClient
    from Services.layer0_ingestion import Layer0IngestionPipeline
    from Services.layer0_ingestion.stores.telemetry_store import write_full_history_snapshots
    from Services.result_publisher import ResultPublisherPipeline
    from Services.telemetry_runtime_simulator import (
        DEFAULT_MOCK_DATE_KEY,
        DEMO_BASELINE_END_HOUR,
        TelemetryRuntimeBatchInjectResult,
        TelemetryRuntimeTemplateInjector,
    )
except ModuleNotFoundError:
    from ...Core import Layer25FusionPipeline, PreprocessingPipeline
    from ...Config.runtime import BackendSettings
    from ..clients import FirebaseRTDBClient
    from ..layer0_ingestion import Layer0IngestionPipeline
    from ..layer0_ingestion.stores.telemetry_store import write_full_history_snapshots
    from ..result_publisher import ResultPublisherPipeline
    from ..telemetry_runtime_simulator import (
        DEFAULT_MOCK_DATE_KEY,
        DEMO_BASELINE_END_HOUR,
        TelemetryRuntimeBatchInjectResult,
        TelemetryRuntimeTemplateInjector,
    )


@dataclass(frozen=True)
class TelemetryServerCycleResult:
    status: str
    injected_template_name: str | None
    export_status: str | None
    layer1_status: str | None
    layer25_status: str | None
    result_status: str | None
    result_label: str | None
    telemetry_path: str | None
    result_path: str | None
    range_sync_count: int | None = None
    range_start_ts: int | None = None
    range_end_ts: int | None = None


@dataclass(frozen=True)
class TelemetryDemoBootstrapResult:
    status: str
    injected_template_name: str
    export_status: str | None
    layer1_status: str | None
    layer25_status: str | None
    telemetry_first_path: str | None
    telemetry_last_path: str | None
    range_sync_count: int
    range_start_ts: int
    range_end_ts: int


class TelemetryServerCyclePipeline:
    def __init__(self, *, settings: BackendSettings, firebase_service: FirebaseRTDBClient):
        self.settings = settings
        self.firebase_service = firebase_service

    def bootstrap_demo_day(
        self,
        *,
        inject_date_key: str = DEFAULT_MOCK_DATE_KEY,
        include_layer25: bool = False,
    ) -> TelemetryDemoBootstrapResult:
        print("[demo-bootstrap] stage 1/4 -> injecting 00:00-12:00 baseline")
        injected = TelemetryRuntimeTemplateInjector(
            settings=self.settings,
            firebase_service=self.firebase_service,
        ).run_bootstrap_day(inject_date_key=inject_date_key)

        print("[demo-bootstrap] stage 2/4 -> syncing baseline range to layer0 history")
        range_sync_count = self._sync_day_range_to_layer0(
            date_key=inject_date_key,
            start_ts=injected.start_sample_ts,
            end_ts=injected.end_sample_ts,
        )

        print("[demo-bootstrap] stage 3/4 -> refreshing latest payload/meta")
        export_result = Layer0IngestionPipeline(
            firebase_client=self.firebase_service,
            settings=self.settings,
        ).run(full_history=False)

        include_meteo_archive = self._meteo_archive_store_exists(self.settings.base_dir)
        print("[demo-bootstrap] stage 4/4 -> layer1 preprocessing")
        layer1_result = PreprocessingPipeline(
            base_dir=self.settings.base_dir,
            include_meteo_archive=include_meteo_archive,
        ).run()

        layer25_status: str | None = None
        if include_layer25:
            print("[demo-bootstrap] optional -> layer2.5 fusion")
            layer25_status = Layer25FusionPipeline().run().status

        return TelemetryDemoBootstrapResult(
            status="completed",
            injected_template_name=injected.template_name,
            export_status=None if export_result is None else export_result.status,
            layer1_status=layer1_result.status,
            layer25_status=layer25_status,
            telemetry_first_path=injected.telemetry_paths[0] if injected.telemetry_paths else None,
            telemetry_last_path=injected.telemetry_paths[-1] if injected.telemetry_paths else None,
            range_sync_count=range_sync_count,
            range_start_ts=injected.start_sample_ts,
            range_end_ts=injected.end_sample_ts,
        )

    def run_demo_cycle(
        self,
        *,
        template_id: int,
        packet_gap_minutes: int = 64,
        inject_date_key: str = DEFAULT_MOCK_DATE_KEY,
        include_layer25: bool = True,
        result_mode: str = "append",
    ) -> TelemetryServerCycleResult:
        print("[server-demo] stage 1/5 -> injecting event episode")
        injected = TelemetryRuntimeTemplateInjector(
            settings=self.settings,
            firebase_service=self.firebase_service,
        ).run_episode(
            template_id=template_id,
            packet_gap_minutes=packet_gap_minutes,
            inject_date_key=inject_date_key,
        )

        range_start_ts = self._noon_start_ts(inject_date_key)
        range_end_ts = injected.end_sample_ts

        print("[server-demo] stage 2/5 -> syncing post-12h telemetry range to layer0 history")
        range_sync_count = self._sync_day_range_to_layer0(
            date_key=inject_date_key,
            start_ts=range_start_ts,
            end_ts=range_end_ts,
        )

        print("[server-demo] stage 3/5 -> refreshing latest payload/meta")
        export_result = Layer0IngestionPipeline(
            firebase_client=self.firebase_service,
            settings=self.settings,
        ).run(full_history=False)
        if export_result is None:
            return TelemetryServerCycleResult(
                status="no_source_data",
                injected_template_name=injected.template_name,
                export_status=None,
                layer1_status=None,
                layer25_status=None,
                result_status=None,
                result_label=None,
                telemetry_path=injected.telemetry_paths[-1] if injected.telemetry_paths else None,
                result_path=None,
                range_sync_count=range_sync_count,
                range_start_ts=range_start_ts,
                range_end_ts=range_end_ts,
            )

        include_meteo_archive = self._meteo_archive_store_exists(self.settings.base_dir)
        print("[server-demo] stage 4/5 -> layer1 preprocessing")
        layer1_result = PreprocessingPipeline(
            base_dir=self.settings.base_dir,
            include_meteo_archive=include_meteo_archive,
        ).run()

        layer25_status: str | None = None
        if include_layer25:
            print("[server-demo] optional -> layer2.5 fusion")
            layer25_status = Layer25FusionPipeline().run().status

        print("[server-demo] stage 5/5 -> result publish")
        publish_result = ResultPublisherPipeline(
            settings=self.settings,
            firebase_service=self.firebase_service,
        ).run(mode=result_mode, dry_run=False)

        return TelemetryServerCycleResult(
            status="completed",
            injected_template_name=injected.template_name,
            export_status=export_result.status,
            layer1_status=layer1_result.status,
            layer25_status=layer25_status,
            result_status=publish_result.status,
            result_label=publish_result.diagnosis_label,
            telemetry_path=injected.telemetry_paths[-1] if injected.telemetry_paths else None,
            result_path=publish_result.result_path,
            range_sync_count=range_sync_count,
            range_start_ts=range_start_ts,
            range_end_ts=range_end_ts,
        )

    def run_once(
        self,
        *,
        template_id: int | None = None,
        packet_gap_minutes: int = 64,
        inject_date_key: str = DEFAULT_MOCK_DATE_KEY,
        include_layer25: bool = True,
        result_mode: str = "append",
    ) -> TelemetryServerCycleResult:
        injected_template_name: str | None = None
        telemetry_path: str | None = None
        if template_id is not None:
            print("[server-cycle] injecting telemetry template ...")
            injected = TelemetryRuntimeTemplateInjector(
                settings=self.settings,
                firebase_service=self.firebase_service,
            ).run(
                template_id=template_id,
                packet_gap_minutes=packet_gap_minutes,
                inject_date_key=inject_date_key,
            )
            injected_template_name = injected.template_name
            telemetry_path = injected.telemetry_path

        print("[server-cycle] stage 1/4 -> latest-only export")
        export_result = Layer0IngestionPipeline(
            firebase_client=self.firebase_service,
            settings=self.settings,
        ).run(full_history=False)
        if export_result is None:
            return TelemetryServerCycleResult(
                status="no_source_data",
                injected_template_name=injected_template_name,
                export_status=None,
                layer1_status=None,
                layer25_status=None,
                result_status=None,
                result_label=None,
                telemetry_path=telemetry_path,
                result_path=None,
            )

        if export_result.status not in {"new_data", "source_refresh"}:
            return TelemetryServerCycleResult(
                status="no_new_telemetry",
                injected_template_name=injected_template_name,
                export_status=export_result.status,
                layer1_status=None,
                layer25_status=None,
                result_status=None,
                result_label=None,
                telemetry_path=telemetry_path,
                result_path=None,
            )

        include_meteo_archive = self._meteo_archive_store_exists(self.settings.base_dir)
        print("[server-cycle] stage 2/4 -> layer1 preprocessing")
        layer1_result = PreprocessingPipeline(
            base_dir=self.settings.base_dir,
            include_meteo_archive=include_meteo_archive,
        ).run()

        layer25_status: str | None = None
        if include_layer25:
            print("[server-cycle] stage 3/4 -> layer2.5 fusion")
            layer25_status = Layer25FusionPipeline().run().status

        print("[server-cycle] stage 4/4 -> result publish")
        publish_result = ResultPublisherPipeline(
            settings=self.settings,
            firebase_service=self.firebase_service,
        ).run(mode=result_mode, dry_run=False)

        return TelemetryServerCycleResult(
            status="completed",
            injected_template_name=injected_template_name,
            export_status=export_result.status,
            layer1_status=layer1_result.status,
            layer25_status=layer25_status,
            result_status=publish_result.status,
            result_label=publish_result.diagnosis_label,
            telemetry_path=telemetry_path,
            result_path=publish_result.result_path,
        )

    def _sync_day_range_to_layer0(self, *, date_key: str, start_ts: int, end_ts: int) -> int:
        day_payload = self.firebase_service.pull_data(node_path=f"{self.settings.telemetry_root_path}/{date_key}")
        if not isinstance(day_payload, dict):
            return 0
        checked_at = datetime.utcnow()
        return write_full_history_snapshots(
            settings=self.settings,
            telemetry_payload={date_key: day_payload},
            checked_at=checked_at,
            start_ts=start_ts,
            end_ts=end_ts,
        )

    def _noon_start_ts(self, inject_date_key: str) -> int:
        local_dt = datetime.strptime(inject_date_key, "%Y-%m-%d").replace(
            hour=DEMO_BASELINE_END_HOUR,
            minute=0,
            second=0,
            tzinfo=self.settings.timezone,
        )
        return int(local_dt.timestamp())

    def _meteo_archive_store_exists(self, layer0_root: Path) -> bool:
        history_root = layer0_root / "history"
        new_raw_root = layer0_root / "new_raw"
        return (
            (history_root.exists() and any(history_root.rglob("*.json")))
            or (new_raw_root / "latest.json").exists()
            or (new_raw_root / "latest_meta.json").exists()
        )
