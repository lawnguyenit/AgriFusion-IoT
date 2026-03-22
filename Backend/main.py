import argparse


if __package__:
    from .Services.exporters import ExportPipeline
    from .Services.firebase_service import FirebaseService
else:
    from Services.exporters import ExportPipeline
    from Services.firebase_service import FirebaseService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pull latest Firebase data or optionally hydrate full telemetry history."
    )
    parser.add_argument(
        "--full-history",
        action="store_true",
        help="Also pull the full Node2/telemetry tree into local history storage.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
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


if __name__ == "__main__":
    main()
