import argparse
from datetime import date, timedelta


if __package__:
    from .Core import Layer25FusionPipeline, PreprocessingPipeline
    from .Services.config.settings import SETTINGS, ExportSettings
else:
    from Core import Layer25FusionPipeline, PreprocessingPipeline
    from Services.config.settings import SETTINGS, ExportSettings


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
        help="Also preprocess ERA5 archive into a separate Layer1/meteo_archive_era5 folder.",
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


def normalize_layer_name(value: str) -> str:
    normalized = value.strip().lower().replace("_", "").replace("-", "")
    if normalized not in LAYER_ALIASES:
        raise ValueError(f"Unknown layer '{value}'. Use layer0, layer1, or layer2.5.")
    return LAYER_ALIASES[normalized]


def resolve_layer_plan(args: argparse.Namespace) -> tuple[bool, bool, bool]:
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


def build_runtime_settings(args: argparse.Namespace) -> ExportSettings:
    node_slug_override = args.node_slug
    if args.node_id is not None and args.node_slug is None:
        node_slug_override = ""

    settings = SETTINGS.with_overrides(
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


def sync_meteo_layer0(args: argparse.Namespace) -> None:
    if __package__:
        from .Services.exporters.sources.open_meteo import (
            build_archive_era5_settings,
            get_local_today,
            run_archive_era5_sync,
            run_forecast_ifs_range_sync,
            run_forecast_ifs_sync,
        )
    else:
        from Services.exporters.sources.open_meteo import (
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
            print_result(
                "Open-Meteo ERA5 archive",
                run_archive_era5_sync(
                    force_full_sync=args.full_history or explicit_date_range,
                    start_date_override=archive_start,
                    end_date_override=archive_end,
                ),
            )
        elif explicit_date_range:
            print("--- Bo qua ERA5 archive vi khoang ngay nam trong vung du lieu qua moi ---")


def run_layer0(args: argparse.Namespace, settings: ExportSettings) -> bool:
    if __package__:
        from .Services.exporters import ExportPipeline
        from .Services.clients.firebase import FirebaseService
    else:
        from Services.exporters import ExportPipeline
        from Services.clients.firebase import FirebaseService

    history_start_date, history_end_date = get_source_date_range(args)
    date_window_requested = history_start_date is not None or history_end_date is not None
    firebase_full_history = args.full_history or date_window_requested

    firebase_service = None
    if settings.source_type == "firebase":
        firebase_service = FirebaseService()

    pipeline = ExportPipeline(firebase_service=firebase_service, settings=settings)

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


def run_layer1(args: argparse.Namespace, settings: ExportSettings) -> None:
    layer1_result = PreprocessingPipeline(
        base_dir=settings.base_dir,
        include_meteo_archive=args.include_meteo_archive_layer1,
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


def main() -> None:
    args = parse_args()
    if (args.meteo_start_date is not None or args.meteo_end_date is not None) and not args.sync_meteo:
        args.sync_meteo = True
        print("--- Tu dong bat --sync-meteo vi co meteo start/end date ---")

    settings = build_runtime_settings(args)
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


if __name__ == "__main__":
    main()
