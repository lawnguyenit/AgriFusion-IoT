import argparse
from datetime import date, timedelta
from pathlib import Path


if __package__:
    from .Core import Layer25FusionPipeline, PreprocessingPipeline
    from .Config.runtime import BACKEND_SETTINGS, BackendSettings
else:
    from Core import Layer25FusionPipeline, PreprocessingPipeline
    from Config.runtime import BACKEND_SETTINGS, BackendSettings


LAYER_ALIASES = {
    "0": "layer0",
    "l0": "layer0",
    "layer0": "layer0",
    "1": "layer1",
    "l1": "layer1",
    "layer1": "layer1",
    "2.5": "layer25",
    "25": "layer25",
    "l25": "layer25",
    "layer25": "layer25",
    "layer2.5": "layer25",
}
LAYER_ORDER = {"layer0": 0, "layer1": 1, "layer25": 2}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run AgriFusion data layers independently or as a Layer0 -> Layer1 -> Layer2.5 pipeline."
    )
    parser.add_argument(
        "--target-layer",
        "--to-layer",
        dest="target_layer",
        help="Run from Layer0 through this target layer: layer0, layer1, or layer2.5.",
    )
    parser.add_argument(
        "--only-layer0",
        action="store_true",
        help="Run only Layer0 raw ingestion from configured sources.",
    )
    parser.add_argument(
        "--only-layer1",
        action="store_true",
        help="Run only Layer1 preprocessing from local Layer0 artifacts.",
    )
    parser.add_argument(
        "--only-layer25",
        "--only-layer2.5",
        dest="only_layer25",
        action="store_true",
        help="Run only Layer2.5 fusion from local Layer1 artifacts.",
    )
    parser.add_argument(
        "--latest-only",
        action="store_true",
        help="Do not backfill Firebase/JSON history; sync only the latest raw payload before downstream layers.",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default=None,
        help="Generic backfill start date in YYYY-MM-DD. Missing start means from the first available record.",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default=None,
        help="Generic backfill end date in YYYY-MM-DD. Missing end means sync to the latest available data.",
    )
    parser.add_argument(
        "--source",
        choices=("firebase", "json-export"),
        help="Layer0 source adapter. Defaults to EXPORT_SOURCE or firebase.",
    )
    parser.add_argument(
        "--input-json",
        help="Path to a Firebase RTDB export JSON file. Required when --source json-export.",
    )
    parser.add_argument(
        "--node-id",
        help="Logical node id used for Layer0 metadata paths, such as Node1 or Node2.",
    )
    parser.add_argument(
        "--node-slug",
        help="Filesystem-safe node slug used in history filenames, such as node1 or node2.",
    )
    parser.add_argument(
        "--npk-sensor-id",
        help="Explicit NPK sensor id injected into JSON-export payloads when missing.",
    )
    parser.add_argument(
        "--npk-sensor-type",
        help="Explicit NPK sensor type injected into JSON-export payloads when missing.",
    )
    parser.add_argument(
        "--sht30-sensor-id",
        help="Explicit SHT30 sensor id injected into JSON-export payloads when missing.",
    )
    parser.add_argument(
        "--sht30-sensor-type",
        help="Explicit SHT30 sensor type injected into JSON-export payloads when missing.",
    )
    parser.add_argument(
        "--full-history",
        action="store_true",
        help="Materialize full source history. With --start-date/--end-date, only dates in that window are written.",
    )
    parser.add_argument(
        "--sync-meteo",
        action="store_true",
        help="Also sync Open-Meteo IFS forecast and ERA5 archive data into Layer0.",
    )
    parser.add_argument(
        "--meteo-mode",
        choices=("all", "forecast", "archive"),
        default="all",
        help="Which Open-Meteo source to sync when --sync-meteo is enabled.",
    )
    parser.add_argument(
        "--meteo-start-date",
        type=str,
        default=None,
        help="Open-Meteo-specific start date in YYYY-MM-DD. Overrides --start-date for meteo only.",
    )
    parser.add_argument(
        "--meteo-end-date",
        type=str,
        default=None,
        help="Open-Meteo-specific end date in YYYY-MM-DD. Overrides --end-date for meteo only.",
    )
    parser.add_argument(
        "--meteo-archive-days",
        type=int,
        default=5,
        help="Default number of ERA5 archive days to sync when no archive date range is given.",
    )
    parser.add_argument(
        "--include-meteo-archive-layer1",
        action="store_true",
        help="Force include ERA5 archive in Layer1 meteo stitching. Archive is auto-enabled when history already exists.",
    )
    parser.add_argument(
        "--layer2-only",
        action="store_true",
        help="Deprecated alias for skipping Layer0 and running downstream preprocessing from local data.",
    )
    parser.add_argument(
        "--skip-layer2",
        action="store_true",
        help="Deprecated alias for stopping after Layer0 ingestion.",
    )
    parser.add_argument(
        "--skip-layer25",
        action="store_true",
        help="Deprecated alias for stopping before Layer2.5 fusion.",
    )
    parser.add_argument(
        "--publish-result",
        action="store_true",
        help="Publish local Layer1 artifacts to Firebase RTDB under the result branch for frontend consumption.",
    )
    parser.add_argument(
        "--result-mode",
        choices=("snapshot", "append"),
        default="snapshot",
        help="Result publish mode: snapshot bootstraps all history, append only pushes records newer than the last publish state.",
    )
    parser.add_argument(
        "--result-dry-run",
        action="store_true",
        help="Build the result payload and local manifest without writing to Firebase RTDB.",
    )
    parser.add_argument(
        "--only-result",
        action="store_true",
        help="Skip Layer0/Layer1/Layer2.5 and publish result from existing local artifacts only.",
    )
    parser.add_argument(
        "--inject-telemetry-template",
        type=int,
        choices=tuple(range(5)),
        help="Inject one demo telemetry template into Firebase telemetry: 0 normal, 1 packet-loss gap, 2 water-deficit, 3 rain-humid, 4 fertigation-like.",
    )
    parser.add_argument(
        "--inject-packet-gap-minutes",
        type=int,
        default=64,
        help="Gap in minutes used by template 1 to simulate packet-loss/outage continuity.",
    )
    parser.add_argument(
        "--inject-date-key",
        type=str,
        default="2026-05-20",
        help="Date key used for injected mock telemetry in YYYY-MM-DD. Defaults to 2026-05-20 for easy cleanup.",
    )
    parser.add_argument(
        "--server-cycle-once",
        action="store_true",
        help="Run one full server lifecycle: optional telemetry template injection, latest-only export, Layer1, optional Layer2.5, FT result publish.",
    )
    parser.add_argument(
        "--demo-bootstrap-day",
        action="store_true",
        help="Inject a deterministic normal baseline for 2026-05-20 00:00->12:00, sync it into Layer0/Layer1, and prepare local demo history.",
    )
    parser.add_argument(
        "--server-cycle-demo",
        action="store_true",
        help="Inject a post-12h demo episode for the selected template, sync that ts range from Firebase, run Layer1, and publish FT result.",
    )
    parser.add_argument(
        "--server-cycle-skip-layer25",
        action="store_true",
        help="When --server-cycle-once is used, skip Layer2.5 fusion and only refresh Layer0/Layer1/result.",
    )

    args = parser.parse_args()
    validate_args(args, parser)
    return args


def validate_args(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    only_layers = [args.only_layer0, args.only_layer1, args.only_layer25]
    if sum(1 for enabled in only_layers if enabled) > 1:
        parser.error("Use only one of --only-layer0, --only-layer1, or --only-layer2.5.")

    if args.target_layer is not None:
        try:
            args.target_layer = normalize_layer_name(args.target_layer)
        except ValueError as exc:
            parser.error(str(exc))

    if args.latest_only and args.full_history:
        parser.error("--latest-only cannot be combined with --full-history.")
    if args.latest_only and (
        args.start_date is not None
        or args.end_date is not None
        or args.meteo_start_date is not None
        or args.meteo_end_date is not None
    ):
        parser.error("--latest-only cannot be combined with date-range options.")
    if args.only_result and not args.publish_result:
        parser.error("--only-result requires --publish-result.")
    if args.result_dry_run and not args.publish_result:
        parser.error("--result-dry-run requires --publish-result.")
    if args.server_cycle_once and args.only_result:
        parser.error("--server-cycle-once cannot be combined with --only-result.")
    if args.demo_bootstrap_day and args.server_cycle_once:
        parser.error("--demo-bootstrap-day cannot be combined with --server-cycle-once.")
    if args.demo_bootstrap_day and args.server_cycle_demo:
        parser.error("--demo-bootstrap-day cannot be combined with --server-cycle-demo.")
    if args.server_cycle_demo and args.server_cycle_once:
        parser.error("--server-cycle-demo cannot be combined with --server-cycle-once.")
    if args.server_cycle_demo and args.inject_telemetry_template is None:
        parser.error("--server-cycle-demo requires --inject-telemetry-template.")
    try:
        date.fromisoformat(args.inject_date_key)
    except ValueError:
        parser.error(f"--inject-date-key must use YYYY-MM-DD, got: {args.inject_date_key}")


def normalize_layer_name(value: str) -> str:
    normalized = value.strip().lower().replace("_", "").replace("-", "")
    if normalized not in LAYER_ALIASES:
        raise ValueError(f"Unknown layer '{value}'. Use layer0, layer1, or layer2.5.")
    return LAYER_ALIASES[normalized]


def resolve_layer_plan(args: argparse.Namespace) -> tuple[bool, bool, bool]:
    if args.only_result:
        return False, False, False
    if args.only_layer0:
        return True, False, False
    if args.only_layer1:
        return False, True, False
    if args.only_layer25:
        return False, False, True

    if args.target_layer is not None:
        target_order = LAYER_ORDER[args.target_layer]
        return (
            target_order >= LAYER_ORDER["layer0"],
            target_order >= LAYER_ORDER["layer1"],
            target_order >= LAYER_ORDER["layer25"],
        )

    run_layer0 = not args.layer2_only
    run_layer1 = not args.skip_layer2
    run_layer25 = run_layer1 and not args.skip_layer25
    return run_layer0, run_layer1, run_layer25


def build_runtime_settings(args: argparse.Namespace) -> BackendSettings:
    node_slug_override = args.node_slug
    if args.node_id is not None and args.node_slug is None:
        node_slug_override = ""

    settings = BACKEND_SETTINGS.with_overrides(
        source_type=args.source,
        input_json_path=args.input_json,
        node_id=args.node_id,
        node_slug=node_slug_override,
        npk_sensor_id=args.npk_sensor_id,
        npk_sensor_type=args.npk_sensor_type,
        sht30_sensor_id=args.sht30_sensor_id,
        sht30_sensor_type=args.sht30_sensor_type,
    )

    if settings.source_type == "json-export" and settings.input_json_path is None:
        raise ValueError("--input-json is required when --source json-export")

    return settings


def parse_date_argument(value: str | None, field_name: str) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must use YYYY-MM-DD, got: {value}") from exc


def ordered_date_range(start_date: date | None, end_date: date | None) -> tuple[date | None, date | None]:
    if start_date is not None and end_date is not None and start_date > end_date:
        return end_date, start_date
    return start_date, end_date


def get_source_date_range(args: argparse.Namespace) -> tuple[date | None, date | None]:
    return ordered_date_range(
        parse_date_argument(args.start_date, "--start-date"),
        parse_date_argument(args.end_date, "--end-date"),
    )


def get_meteo_date_range(args: argparse.Namespace) -> tuple[date | None, date | None]:
    start_value = args.meteo_start_date if args.meteo_start_date is not None else args.start_date
    end_value = args.meteo_end_date if args.meteo_end_date is not None else args.end_date
    return ordered_date_range(
        parse_date_argument(start_value, "--meteo-start-date"),
        parse_date_argument(end_value, "--meteo-end-date"),
    )


def has_any_json_files(root: Path) -> bool:
    return root.exists() and any(root.rglob("*.json"))


def meteo_archive_history_exists(settings: object) -> bool:
    return has_any_json_files(settings.history_root)


def meteo_archive_store_exists(settings: object) -> bool:
    archive_root = settings.base_dir
    new_raw_root = archive_root / "new_raw"
    return (
        has_any_json_files(settings.history_root)
        or (new_raw_root / "latest.json").exists()
        or (new_raw_root / "latest_meta.json").exists()
    )


def sync_meteo_layer0(args: argparse.Namespace) -> None:
    if __package__:
        from .Services.layer0_ingestion.sources.open_meteo import (
            build_archive_era5_settings,
            get_local_today,
            run_archive_era5_sync,
            run_forecast_ifs_range_sync,
            run_forecast_ifs_sync,
        )
    else:
        from Services.layer0_ingestion.sources.open_meteo import (
            build_archive_era5_settings,
            get_local_today,
            run_archive_era5_sync,
            run_forecast_ifs_range_sync,
            run_forecast_ifs_sync,
        )

    def print_result(label: str, result: dict[str, object]) -> None:
        print(f"--- {label} ---")
        print(f"Meteo sync status: {result['status']}")
        print(f"Meteo run mode: {result['run_mode']}")
        print(f"Meteo fetch window: {result['fetch_start_date']} -> {result['fetch_end_date']}")
        print(f"Meteo fetched records: {result['fetched_record_count']}")
        print(f"Meteo written records: {result['written_record_count']}")
        print(f"Meteo history root: {result['history_root']}")
        print(f"Meteo latest payload: {result['latest_payload_path']}")
        print(f"Meteo latest meta: {result['latest_meta_path']}")

    print("--- Dang keo du lieu Open-Meteo vao Layer0 ---")

    archive_settings = build_archive_era5_settings()
    requested_start, requested_end = get_meteo_date_range(args)
    explicit_date_range = requested_start is not None or requested_end is not None
    local_today = get_local_today(archive_settings)
    era_available_until = local_today - timedelta(days=5)
    archive_history_exists = meteo_archive_history_exists(archive_settings)

    if explicit_date_range:
        range_start = requested_start or archive_settings.default_start_date
        range_end = requested_end or local_today
        range_start, range_end = ordered_date_range(range_start, range_end)

        archive_start = range_start
        archive_end = min(range_end, era_available_until)
        forecast_start = max(range_start, era_available_until + timedelta(days=1))
        forecast_end = range_end
    else:
        archive_end = era_available_until
        archive_days = max(1, int(args.meteo_archive_days))
        archive_start = (
            archive_settings.default_start_date
            if args.full_history
            else archive_end - timedelta(days=archive_days - 1)
        )
        forecast_start = None
        forecast_end = None

    if args.meteo_mode in {"all", "forecast"}:
        if explicit_date_range:
            if forecast_start <= forecast_end:
                print_result(
                    "Open-Meteo IFS forecast",
                    run_forecast_ifs_range_sync(
                        start_date_override=forecast_start,
                        end_date_override=forecast_end,
                    ),
                )
            else:
                print("--- Bo qua IFS forecast vi khoang ngay nam trong vung ERA5 archive ---")
        else:
            print_result(
                "Open-Meteo IFS forecast hien tai",
                run_forecast_ifs_sync(),
            )

    if args.meteo_mode in {"all", "archive"}:
        if archive_start <= archive_end:
            should_sync_archive = (
                explicit_date_range
                or args.full_history
                or args.meteo_mode == "archive"
                or not archive_history_exists
            )
            if should_sync_archive:
                print_result(
                    "Open-Meteo ERA5 archive",
                    run_archive_era5_sync(
                        force_full_sync=args.full_history or explicit_date_range,
                        start_date_override=archive_start,
                        end_date_override=archive_end,
                    ),
                )
            else:
                print("--- Bo qua ERA5 archive: da co lich su bootstrap, chi can forecast/latest de mo rong ---")
        elif explicit_date_range:
            print("--- Bo qua ERA5 archive vi khoang ngay nam trong vung du lieu qua moi ---")


def run_layer0(args: argparse.Namespace, settings: BackendSettings) -> bool:
    if __package__:
        from .Services.clients import FirebaseRTDBClient
        from .Services.layer0_ingestion import Layer0IngestionPipeline
    else:
        from Services.clients import FirebaseRTDBClient
        from Services.layer0_ingestion import Layer0IngestionPipeline

    history_start_date, history_end_date = get_source_date_range(args)
    date_window_requested = history_start_date is not None or history_end_date is not None
    firebase_full_history = args.full_history or date_window_requested

    firebase_service = None
    if settings.source_type == "firebase":
        firebase_service = FirebaseRTDBClient()

    pipeline = Layer0IngestionPipeline(firebase_client=firebase_service, settings=settings)

    print("--- Dang bat dau tien trinh Layer0 ingestion ---")
    print(f"Source adapter: {settings.source_type}")
    print(f"Node id: {settings.node_id}")
    if settings.source_type == "json-export":
        print(f"Input JSON: {settings.input_json_path}")
    if firebase_full_history:
        start_label = history_start_date.isoformat() if history_start_date is not None else "first available"
        end_label = history_end_date.isoformat() if history_end_date is not None else "latest available"
        print(f"History window: {start_label} -> {end_label}")
    else:
        print("History window: latest payload only")

    result = pipeline.run(
        full_history=firebase_full_history,
        history_start_date=history_start_date,
        history_end_date=history_end_date,
    )

    if result is None:
        print("That bai! Kiem tra package Python, ket noi mang, va cau hinh Layer0 trong Services/.env hoac CLI.")
        return False

    print(f"Sync status: {result.status}")
    print(f"Checked at UTC: {result.checked_at_utc}")
    print(f"Latest event key: {result.latest_event_key}")
    print(f"Latest RTDB path: {result.latest_path}")
    print(f"Latest meta saved to: {result.latest_meta_local_path}")
    print(f"Sync state saved to: {result.sync_state_path}")
    print(f"Source manifest saved to: {result.source_manifest_path}")

    if result.source_snapshot_path is not None:
        print(f"Source snapshot saved to: {result.source_snapshot_path}")
    if result.next_retry_at_utc:
        print(f"Next retry UTC: {result.next_retry_at_utc}")
    if result.next_primary_check_at_utc:
        print(f"Next primary check UTC: {result.next_primary_check_at_utc}")
    if result.latest_payload_path is not None:
        print(f"Latest payload saved to: {result.latest_payload_path}")
    if result.history_path is not None:
        print(f"History snapshot saved to: {result.history_path}")
    if firebase_full_history:
        print(f"Full history files written: {result.full_history_written_count}")

    if args.sync_meteo:
        sync_meteo_layer0(args)

    return True


def run_layer1(args: argparse.Namespace, settings: BackendSettings) -> None:
    include_meteo_archive = args.include_meteo_archive_layer1 or meteo_archive_store_exists(settings)
    if include_meteo_archive and not args.include_meteo_archive_layer1:
        print("--- Tu dong bao gom ERA5 archive vao Layer1 meteo vi da co history ---")

    layer1_result = PreprocessingPipeline(
        base_dir=settings.base_dir,
        include_meteo_archive=include_meteo_archive,
    ).run()
    print("--- Layer1 preprocessing hoan tat ---")
    print(f"Layer1 status: {layer1_result.status}")
    print(f"Processed source records: {layer1_result.processed_source_records}")
    print(f"Filtered source records: {layer1_result.filtered_out_records}")
    print(f"New layer1 snapshots: {layer1_result.total_new_snapshots}")
    print(f"Layer1 output root: {layer1_result.output_root}")
    print(f"Layer1 manifest: {layer1_result.manifest_path}")
    for sensor_key, count in sorted(layer1_result.sensor_counts.items()):
        print(f"  {sensor_key}: {count}")


def run_layer25() -> None:
    layer25_result = Layer25FusionPipeline().run()
    print("--- Layer2.5 fusion hoan tat ---")
    print(f"Layer2.5 status: {layer25_result.status}")
    print(f"Layer2.5 source snapshots: {layer25_result.source_snapshot_count}")
    print(f"Layer2.5 fused rows: {layer25_result.fused_row_count}")
    print(f"Layer2.5 output root: {layer25_result.output_root}")
    print(f"Layer2.5 manifest: {layer25_result.manifest_path}")
    print(f"Layer2.5 latest: {layer25_result.latest_path}")
    print(f"Layer2.5 JSONL: {layer25_result.jsonl_path}")
    print(f"Layer2.5 CSV: {layer25_result.csv_path}")


def run_result_publish(args: argparse.Namespace, settings: BackendSettings) -> None:
    if __package__:
        from .Services.result_publisher import ResultPublisherPipeline
    else:
        from Services.result_publisher import ResultPublisherPipeline

    firebase_service = None
    if not args.result_dry_run:
        if __package__:
            from .Services.clients import FirebaseRTDBClient
        else:
            from Services.clients import FirebaseRTDBClient
        firebase_service = FirebaseRTDBClient()
    publisher = ResultPublisherPipeline(settings=settings, firebase_service=firebase_service)
    publish_result = publisher.run(mode=args.result_mode, dry_run=args.result_dry_run)

    print("--- Result publisher hoan tat ---")
    print(f"Result status: {publish_result.status}")
    print(f"Requested mode: {publish_result.requested_mode}")
    print(f"Effective mode: {publish_result.effective_mode}")
    print(f"Dry run: {publish_result.dry_run}")
    print(f"Result path: {publish_result.result_path}")
    print(f"Last published ts: {publish_result.last_published_ts}")
    print(f"Diagnosis label: {publish_result.diagnosis_label}")
    print(f"Diagnosis abnormal probability: {publish_result.diagnosis_probability}")
    print(f"History counts: {publish_result.history_counts}")
    print(f"History last ts: {publish_result.history_last_ts}")
    print(f"Result state path: {publish_result.state_path}")
    print(f"Result payload path: {publish_result.payload_path}")
    print(f"Result manifest path: {publish_result.manifest_path}")


def run_telemetry_template_injection(args: argparse.Namespace, settings: BackendSettings) -> None:
    if __package__:
        from .Services.clients import FirebaseRTDBClient
        from .Services.telemetry_runtime_simulator import TelemetryRuntimeTemplateInjector
    else:
        from Services.clients import FirebaseRTDBClient
        from Services.telemetry_runtime_simulator import TelemetryRuntimeTemplateInjector

    firebase_service = FirebaseRTDBClient()
    injector = TelemetryRuntimeTemplateInjector(settings=settings, firebase_service=firebase_service)
    inject_result = injector.run(
        template_id=int(args.inject_telemetry_template),
        packet_gap_minutes=int(args.inject_packet_gap_minutes),
        inject_date_key=str(args.inject_date_key),
    )
    print("--- Da inject telemetry template vao Firebase ---")
    print(f"Template id: {inject_result.template_id}")
    print(f"Template name: {inject_result.template_name}")
    print(f"Telemetry path: {inject_result.telemetry_path}")
    print(f"Sample ts: {inject_result.sample_ts}")
    print(f"Server ts: {inject_result.server_ts}")
    print(f"Latest meta path: {inject_result.latest_meta_path}")


def run_server_cycle_once(args: argparse.Namespace, settings: BackendSettings) -> None:
    if __package__:
        from .Services.clients import FirebaseRTDBClient
        from .Services.telemetry_orchestrator import TelemetryServerCyclePipeline
    else:
        from Services.clients import FirebaseRTDBClient
        from Services.telemetry_orchestrator import TelemetryServerCyclePipeline

    firebase_service = FirebaseRTDBClient()
    cycle = TelemetryServerCyclePipeline(settings=settings, firebase_service=firebase_service)
    cycle_result = cycle.run_once(
        template_id=args.inject_telemetry_template,
        packet_gap_minutes=int(args.inject_packet_gap_minutes),
        inject_date_key=str(args.inject_date_key),
        include_layer25=not args.server_cycle_skip_layer25,
        result_mode="append",
    )
    print("--- Server cycle hoan tat ---")
    print(f"Cycle status: {cycle_result.status}")
    print(f"Injected template: {cycle_result.injected_template_name}")
    print(f"Telemetry path: {cycle_result.telemetry_path}")
    print(f"Export status: {cycle_result.export_status}")
    print(f"Layer1 status: {cycle_result.layer1_status}")
    print(f"Layer2.5 status: {cycle_result.layer25_status}")
    print(f"Result status: {cycle_result.result_status}")
    print(f"Result label: {cycle_result.result_label}")
    print(f"Result path: {cycle_result.result_path}")


def run_demo_bootstrap_day(args: argparse.Namespace, settings: BackendSettings) -> None:
    if __package__:
        from .Services.clients import FirebaseRTDBClient
        from .Services.telemetry_orchestrator import TelemetryServerCyclePipeline
    else:
        from Services.clients import FirebaseRTDBClient
        from Services.telemetry_orchestrator import TelemetryServerCyclePipeline

    firebase_service = FirebaseRTDBClient()
    cycle = TelemetryServerCyclePipeline(settings=settings, firebase_service=firebase_service)
    result = cycle.bootstrap_demo_day(
        inject_date_key=str(args.inject_date_key),
        include_layer25=not args.server_cycle_skip_layer25,
    )
    print("--- Demo bootstrap 20/5 hoan tat ---")
    print(f"Bootstrap status: {result.status}")
    print(f"Injected template: {result.injected_template_name}")
    print(f"Telemetry first path: {result.telemetry_first_path}")
    print(f"Telemetry last path: {result.telemetry_last_path}")
    print(f"Range sync count: {result.range_sync_count}")
    print(f"Range start ts: {result.range_start_ts}")
    print(f"Range end ts: {result.range_end_ts}")
    print(f"Export status: {result.export_status}")
    print(f"Layer1 status: {result.layer1_status}")
    print(f"Layer2.5 status: {result.layer25_status}")


def run_server_cycle_demo(args: argparse.Namespace, settings: BackendSettings) -> None:
    if __package__:
        from .Services.clients import FirebaseRTDBClient
        from .Services.telemetry_orchestrator import TelemetryServerCyclePipeline
    else:
        from Services.clients import FirebaseRTDBClient
        from Services.telemetry_orchestrator import TelemetryServerCyclePipeline

    firebase_service = FirebaseRTDBClient()
    cycle = TelemetryServerCyclePipeline(settings=settings, firebase_service=firebase_service)
    result = cycle.run_demo_cycle(
        template_id=int(args.inject_telemetry_template),
        packet_gap_minutes=int(args.inject_packet_gap_minutes),
        inject_date_key=str(args.inject_date_key),
        include_layer25=not args.server_cycle_skip_layer25,
        result_mode="append",
    )
    print("--- Server demo cycle hoan tat ---")
    print(f"Cycle status: {result.status}")
    print(f"Injected template: {result.injected_template_name}")
    print(f"Telemetry path: {result.telemetry_path}")
    print(f"Range sync count: {result.range_sync_count}")
    print(f"Range start ts: {result.range_start_ts}")
    print(f"Range end ts: {result.range_end_ts}")
    print(f"Export status: {result.export_status}")
    print(f"Layer1 status: {result.layer1_status}")
    print(f"Layer2.5 status: {result.layer25_status}")
    print(f"Result status: {result.result_status}")
    print(f"Result label: {result.result_label}")
    print(f"Result path: {result.result_path}")


def main() -> None:
    args = parse_args()
    if (args.meteo_start_date is not None or args.meteo_end_date is not None) and not args.sync_meteo:
        args.sync_meteo = True
        print("--- Tu dong bat --sync-meteo vi co meteo start/end date ---")

    settings = build_runtime_settings(args)

    if args.demo_bootstrap_day:
        run_demo_bootstrap_day(args=args, settings=settings)
        return

    if args.server_cycle_demo:
        run_server_cycle_demo(args=args, settings=settings)
        return

    if args.server_cycle_once:
        run_server_cycle_once(args=args, settings=settings)
        return

    if args.inject_telemetry_template is not None:
        run_telemetry_template_injection(args=args, settings=settings)
        return

    run_layer0_flag, run_layer1_flag, run_layer25_flag = resolve_layer_plan(args)

    if run_layer0_flag:
        if not run_layer0(args=args, settings=settings):
            return
    else:
        print("--- Bo qua Layer0, dung du lieu local da co ---")

    if run_layer1_flag:
        run_layer1(args=args, settings=settings)
    else:
        print("--- Bo qua Layer1 preprocessing ---")

    if run_layer25_flag:
        run_layer25()
    else:
        print("--- Bo qua Layer2.5 fusion ---")

    if args.publish_result:
        run_result_publish(args=args, settings=settings)
    else:
        print("--- Bo qua Result publisher ---")


if __name__ == "__main__":
    main()
