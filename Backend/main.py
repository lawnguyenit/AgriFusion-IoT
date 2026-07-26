import argparse
from datetime import date
from typing import Any


if __package__:
    from .Core import PreprocessingPipeline
    from .Config.runtime import BACKEND_SETTINGS, BackendSettings
else:
    from Core import PreprocessingPipeline
    from Config.runtime import BACKEND_SETTINGS, BackendSettings


LAYER_ALIASES = {
    "0": "layer0",
    "l0": "layer0",
    "layer0": "layer0",
    "1": "layer1",
    "l1": "layer1",
    "layer1": "layer1",
}
LAYER_ORDER = {"layer0": 0, "layer1": 1}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run AgriFusion Layer0 ingestion and Layer1 canonical preprocessing."
    )
    parser.add_argument(
        "--target-layer",
        "--to-layer",
        dest="target_layer",
        help="Run from Layer0 through this target layer: layer0 or layer1.",
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
        "--latest-only",
        action="store_true",
        help="Do not backfill history; sync only the latest raw payload before Layer1.",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default=None,
        help="Backfill start date in YYYY-MM-DD. Missing start means from the first available record.",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default=None,
        help="Backfill end date in YYYY-MM-DD. Missing end means through the latest available record.",
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

    args = parser.parse_args()
    validate_args(args, parser)
    return args


def validate_args(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    only_layers = [args.only_layer0, args.only_layer1]
    if sum(1 for enabled in only_layers if enabled) > 1:
        parser.error("Use only one of --only-layer0 or --only-layer1.")

    if args.target_layer is not None:
        try:
            args.target_layer = normalize_layer_name(args.target_layer)
        except ValueError as exc:
            parser.error(str(exc))

    if args.latest_only and args.full_history:
        parser.error("--latest-only cannot be combined with --full-history.")
    if args.latest_only and (args.start_date is not None or args.end_date is not None):
        parser.error("--latest-only cannot be combined with date-range options.")


def normalize_layer_name(value: str) -> str:
    normalized = value.strip().lower().replace("_", "").replace("-", "")
    if normalized not in LAYER_ALIASES:
        raise ValueError(f"Unknown layer '{value}'. Use layer0 or layer1.")
    return LAYER_ALIASES[normalized]


def resolve_layer_plan(args: argparse.Namespace) -> tuple[bool, bool]:
    if args.only_layer0:
        return True, False
    if args.only_layer1:
        return False, True

    if args.target_layer is not None:
        target_order = LAYER_ORDER[args.target_layer]
        return (
            target_order >= LAYER_ORDER["layer0"],
            target_order >= LAYER_ORDER["layer1"],
        )

    return True, True


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


def run_layer0(args: argparse.Namespace, settings: BackendSettings) -> tuple[bool, Any | None]:
    if __package__:
        from .Core.infrastructure import FirebaseRTDBClient
        from .Core.layer0 import Layer0IngestionPipeline
        from .Core.layer1.loaders import FirebaseSourceLoader
    else:
        from Core.infrastructure import FirebaseRTDBClient
        from Core.layer0 import Layer0IngestionPipeline
        from Core.layer1.loaders import FirebaseSourceLoader

    history_start_date, history_end_date = get_source_date_range(args)
    date_window_requested = history_start_date is not None or history_end_date is not None
    full_history = args.full_history or date_window_requested

    firebase_service = None
    if settings.source_type == "firebase":
        firebase_service = FirebaseRTDBClient()

    pipeline = Layer0IngestionPipeline(firebase_client=firebase_service, settings=settings)

    print("--- Dang bat dau tien trinh Layer0 ingestion ---")
    print(f"Source adapter: {settings.source_type}")
    print(f"Node id: {settings.node_id}")
    if settings.source_type == "json-export":
        print(f"Input JSON: {settings.input_json_path}")
    if full_history:
        start_label = history_start_date.isoformat() if history_start_date is not None else "first available"
        end_label = history_end_date.isoformat() if history_end_date is not None else "latest available"
        print(f"History window: {start_label} -> {end_label}")
    else:
        print("History window: latest payload only")

    result = pipeline.run(
        full_history=full_history,
        history_start_date=history_start_date,
        history_end_date=history_end_date,
    )

    if result is None:
        print("That bai! Kiem tra package Python, ket noi mang, va cau hinh Layer0 trong Backend/.env hoac CLI.")
        return False, None

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
    if full_history:
        print(f"Full history files written: {result.full_history_written_count}")

    layer1_source_loader = None
    if (
        full_history
        and settings.source_type == "firebase"
        and pipeline.last_full_history_payload is not None
    ):
        layer1_source_loader = FirebaseSourceLoader.from_payloads(
            base_dir=settings.base_dir,
            node_id=settings.node_id,
            history_payload=pipeline.last_full_history_payload,
            latest_payload=pipeline.last_latest_current_payload,
            latest_meta=pipeline.last_latest_meta_payload,
        )

    return True, layer1_source_loader


def run_layer1(settings: BackendSettings, source_loader: Any | None = None) -> None:
    layer1_result = PreprocessingPipeline(
        base_dir=settings.base_dir,
        source_loader=source_loader,
    ).run()
    print("--- Layer1 preprocessing hoan tat ---")
    print(f"Layer1 status: {layer1_result.status}")
    print(f"Processed source records: {layer1_result.processed_source_records}")
    print(f"Excluded source records: {layer1_result.filtered_out_records}")
    print(f"Canonical records: {layer1_result.canonical_record_count}")
    print(f"Demo records: {layer1_result.demo_record_count}")
    print(f"Latest-compatible rows: {layer1_result.total_new_snapshots}")
    print(f"Layer1 output root: {layer1_result.output_root}")
    print(f"Layer1 manifest: {layer1_result.manifest_path}")
    print(f"Canonical history: {layer1_result.canonical_history_path}")
    print(f"Canonical latest: {layer1_result.canonical_latest_path}")
    for sensor_key, count in sorted(layer1_result.sensor_counts.items()):
        print(f"  {sensor_key}: {count}")


def main() -> None:
    args = parse_args()
    settings = build_runtime_settings(args)

    run_layer0_flag, run_layer1_flag = resolve_layer_plan(args)
    layer1_source_loader = None

    if run_layer0_flag:
        layer0_ok, layer1_source_loader = run_layer0(args=args, settings=settings)
        if not layer0_ok:
            return
    else:
        print("--- Bo qua Layer0, dung du lieu local da co ---")

    if run_layer1_flag:
        run_layer1(settings=settings, source_loader=layer1_source_loader)
    else:
        print("--- Bo qua Layer1 preprocessing ---")


if __name__ == "__main__":
    main()
