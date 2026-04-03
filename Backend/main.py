import argparse


if __package__:
    from .Core.Preprocessors import Layer25FusionPipeline, PreprocessingPipeline
else:
    from Core.Preprocessors import Layer25FusionPipeline, PreprocessingPipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Layer 1 sync, Layer 2 preprocessing, and Layer 2.5 fusion outputs."
    )
    parser.add_argument(
        "--full-history",
        action="store_true",
        help="Also pull the full Node2/telemetry tree into local history storage.",
    )
    parser.add_argument(
        "--layer2-only",
        action="store_true",
        help="Skip Firebase pull and run layer-2 preprocessing from local Layer1 data only.",
    )
    parser.add_argument(
        "--skip-layer2",
        action="store_true",
        help="Only run layer-1 export and skip the preprocessing handoff.",
    )
    parser.add_argument(
        "--skip-layer25",
        action="store_true",
        help="Run through layer 2 only and skip the layer 2.5 fusion table.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    if not args.layer2_only:
        if __package__:
            from .Services.exporters import ExportPipeline
            from .Services.firebase_service import FirebaseService
        else:
            from Services.exporters import ExportPipeline
            from Services.firebase_service import FirebaseService

        fb_service = FirebaseService()
        pipeline = ExportPipeline(firebase_service=fb_service)

        print("--- Dang bat dau tien trinh keo du lieu ---")
        if args.full_history:
            print("Full-history mode: bat")

        result = pipeline.run(full_history=args.full_history)

        if result is None:
            print("That bai! Kiem tra package Python, ket noi mang, va cau hinh trong Services/.env")
            return

        print(f"Sync status: {result.status}")
        print(f"Checked at UTC: {result.checked_at_utc}")
        print(f"Latest event key: {result.latest_event_key}")
        print(f"Latest RTDB path: {result.latest_path}")
        print(f"Latest meta saved to: {result.latest_meta_local_path}")
        print(f"Sync state saved to: {result.sync_state_path}")

        if result.next_retry_at_utc:
            print(f"Next retry UTC: {result.next_retry_at_utc}")
        if result.next_primary_check_at_utc:
            print(f"Next primary check UTC: {result.next_primary_check_at_utc}")
        if result.latest_payload_path is not None:
            print(f"Latest payload saved to: {result.latest_payload_path}")
        if result.history_path is not None:
            print(f"History snapshot saved to: {result.history_path}")
        if args.full_history:
            print(f"Full history files written: {result.full_history_written_count}")
    else:
        print("--- Bo qua layer 1, chay truc tiep layer 2 tu du lieu local ---")

    if args.skip_layer2:
        return

    layer2_result = PreprocessingPipeline().run()
    print("--- Layer 2 preprocessing hoan tat ---")
    print(f"Layer 2 status: {layer2_result.status}")
    print(f"Processed source records: {layer2_result.processed_source_records}")
    print(f"Filtered source records: {layer2_result.filtered_out_records}")
    print(f"New layer2 snapshots: {layer2_result.total_new_snapshots}")
    print(f"Layer2 output root: {layer2_result.output_root}")
    print(f"Layer2 manifest: {layer2_result.manifest_path}")
    for sensor_key, count in sorted(layer2_result.sensor_counts.items()):
        print(f"  {sensor_key}: {count}")

    if args.skip_layer25:
        return

    layer25_result = Layer25FusionPipeline().run()
    print("--- Layer 2.5 fusion hoan tat ---")
    print(f"Layer 2.5 status: {layer25_result.status}")
    print(f"Layer 2.5 source snapshots: {layer25_result.source_snapshot_count}")
    print(f"Layer 2.5 fused rows: {layer25_result.fused_row_count}")
    print(f"Layer 2.5 ready rows: {layer25_result.ready_row_count}")
    print(f"Layer 2.5 output root: {layer25_result.output_root}")
    print(f"Layer 2.5 manifest: {layer25_result.manifest_path}")
    print(f"Layer 2.5 latest: {layer25_result.latest_path}")
    print(f"Layer 2.5 JSONL: {layer25_result.jsonl_path}")
    print(f"Layer 2.5 CSV: {layer25_result.csv_path}")
    print(f"Layer 2.5 TabNet-ready CSV: {layer25_result.ready_csv_path}")


if __name__ == "__main__":
    main()
