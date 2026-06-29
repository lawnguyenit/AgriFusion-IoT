from __future__ import annotations

import argparse
import copy
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

if __package__ and __package__.startswith("Backend."):
    from Backend.Config.runtime import BACKEND_SETTINGS
    from Backend.Services.clients import FirebaseRTDBClient
else:
    from Config.runtime import BACKEND_SETTINGS
    from Services.clients import FirebaseRTDBClient


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Clean demo result/data on Firebase and local output after a 2026-05-20 style web demo."
    )
    parser.add_argument("--demo-date-key", default="2026-05-20", help="Demo telemetry date key to remove.")
    parser.add_argument(
        "--restore-latest-date-key",
        default="2026-05-19",
        help="Real telemetry date key used to restore latest/current/meta/live after cleanup.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print planned actions without writing anything.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    firebase = None if args.dry_run else FirebaseRTDBClient()

    print("--- Demo cleanup start ---")
    print(f"Demo date key: {args.demo_date_key}")
    print(f"Restore latest date key: {args.restore_latest_date_key}")
    print(f"Dry run: {args.dry_run}")

    cleanup_local_output(
        demo_date_key=str(args.demo_date_key),
        restore_latest_date_key=str(args.restore_latest_date_key),
        dry_run=bool(args.dry_run),
    )

    if args.dry_run:
        print("[dry-run] Skip Firebase cleanup.")
    else:
        cleanup_firebase_state(
            firebase=firebase,
            demo_date_key=str(args.demo_date_key),
            restore_latest_date_key=str(args.restore_latest_date_key),
        )

    print("--- Demo cleanup complete ---")


def cleanup_local_output(*, demo_date_key: str, restore_latest_date_key: str, dry_run: bool) -> None:
    output_root = BACKEND_SETTINGS.output_data_root
    layer0_history_day = _layer0_history_day_dir(demo_date_key)
    result_publish_root = output_root / "Result_publish"

    actions: list[str] = []
    if layer0_history_day.exists():
        actions.append(f"remove {layer0_history_day}")
    if result_publish_root.exists():
        actions.append(f"remove {result_publish_root}")

    if actions:
        print("Local cleanup plan:")
        for item in actions:
            print(f"  - {item}")
    else:
        print("Local cleanup plan: nothing to remove.")

    if dry_run:
        return

    if layer0_history_day.exists():
        shutil.rmtree(layer0_history_day)

    if result_publish_root.exists():
        shutil.rmtree(result_publish_root)

    # Reset latest-only raw pointers to the restored real day if the files still exist later.
    new_raw_root = BACKEND_SETTINGS.firebase_new_raw_dir
    for filename in ("latest.json", "latest_meta.json", "sync_state.json", "source_manifest.json", "source_snapshot.json"):
        file_path = new_raw_root / filename
        if file_path.exists():
            file_path.unlink()

    print(f"Removed local demo day folder and Result_publish artifacts. Restore day target remains {restore_latest_date_key}.")


def cleanup_firebase_state(*, firebase: FirebaseRTDBClient, demo_date_key: str, restore_latest_date_key: str) -> None:
    node_id = BACKEND_SETTINGS.node_id
    telemetry_root = BACKEND_SETTINGS.telemetry_root_path

    restore_day_payload = firebase.pull_data(node_path=f"{telemetry_root}/{restore_latest_date_key}")
    if not isinstance(restore_day_payload, dict) or not restore_day_payload:
        raise ValueError(f"Cannot restore latest state: no telemetry found for {restore_latest_date_key}.")

    latest_meta_before = firebase.pull_data(node_path=BACKEND_SETTINGS.latest_meta_path)
    live_root_before = firebase.pull_data(node_path=f"{node_id}/live")
    latest_record, latest_event_key, previous_record, previous_event_key = _select_restore_candidates(restore_day_payload)
    latest_meta_payload = _build_latest_meta_payload(
        latest_meta=latest_meta_before if isinstance(latest_meta_before, dict) else {},
        latest_record=latest_record,
        event_key=latest_event_key,
        date_key=restore_latest_date_key,
        previous_record=previous_record,
        previous_event_key=previous_event_key,
    )
    live_payload = _build_live_payload(
        live_root=live_root_before if isinstance(live_root_before, dict) else {},
        latest_record=latest_record,
        event_key=latest_event_key,
    )

    print("Firebase cleanup actions:")
    print("  - delete result")
    print(f"  - delete {telemetry_root}/{demo_date_key}")
    print(f"  - restore {BACKEND_SETTINGS.latest_current_path} -> {restore_latest_date_key}/{latest_event_key}")
    print(f"  - restore {BACKEND_SETTINGS.latest_meta_path}")
    print(f"  - restore {node_id}/live")
    print(f"  - remove demo status_events under {node_id}/status_events/*_demo")

    firebase.delete_data("result")
    firebase.delete_data(f"{telemetry_root}/{demo_date_key}")
    firebase.set_data(BACKEND_SETTINGS.latest_current_path, latest_record)
    firebase.set_data(BACKEND_SETTINGS.latest_meta_path, latest_meta_payload)
    firebase.set_data(f"{node_id}/live", live_payload)

    status_events = firebase.pull_data(node_path=f"{node_id}/status_events")
    if isinstance(status_events, dict):
        for status_key in list(status_events.keys()):
            if str(status_key).endswith("_demo"):
                firebase.delete_data(f"{node_id}/status_events/{status_key}")


def _layer0_history_day_dir(date_key: str) -> Path:
    target_date = datetime.strptime(date_key, "%Y-%m-%d")
    return (
        BACKEND_SETTINGS.history_root
        / target_date.strftime("%Y")
        / target_date.strftime("%m")
        / target_date.strftime("%d")
    )


def _select_restore_candidates(day_payload: dict[str, Any]) -> tuple[dict[str, Any], str, dict[str, Any] | None, str | None]:
    candidates: list[tuple[int, str, dict[str, Any]]] = []
    for event_key, payload in day_payload.items():
        if not isinstance(payload, dict):
            continue
        ts_value = _resolve_event_timestamp(event_key=event_key, record_payload=payload)
        if ts_value is None:
            continue
        candidates.append((ts_value, str(event_key), payload))

    if not candidates:
        raise ValueError("No valid restore telemetry record found.")

    candidates.sort(key=lambda item: item[0])
    latest_ts, latest_event_key, latest_payload = candidates[-1]
    previous_payload = None if len(candidates) < 2 else candidates[-2][2]
    previous_event_key = None if len(candidates) < 2 else candidates[-2][1]
    return copy.deepcopy(latest_payload), latest_event_key, copy.deepcopy(previous_payload) if previous_payload else None, previous_event_key


def _build_latest_meta_payload(
    *,
    latest_meta: dict[str, Any],
    latest_record: dict[str, Any],
    event_key: str,
    date_key: str,
    previous_record: dict[str, Any] | None,
    previous_event_key: str | None,
) -> dict[str, Any]:
    previous_ts_server = int(
        (previous_record or {}).get("ts_server")
        or latest_meta.get("previous_ts_server")
        or latest_meta.get("ts_server")
        or latest_record["ts_server"]
    )
    previous_ts_device = int(
        (previous_record or {}).get("ts_device")
        or latest_meta.get("previous_ts_device")
        or latest_meta.get("ts_device")
        or latest_record["ts_device"]
    )
    delta_server_sec = int(latest_record["ts_server"]) - previous_ts_server
    delta_device_sec = int(latest_record["ts_device"]) - previous_ts_device
    primary_poll_after_sec = int(latest_meta.get("primary_poll_after_sec") or 900)
    tolerance = max(60, primary_poll_after_sec // 3)
    expected_min = max(0, primary_poll_after_sec - tolerance)
    expected_max = primary_poll_after_sec + tolerance

    return {
        "schema_version": 1,
        "node_id": BACKEND_SETTINGS.node_id,
        "latest_date_key": date_key,
        "latest_event_key": event_key,
        "latest_local_iso": latest_record.get("sample_time_local"),
        "latest_path": f"{BACKEND_SETTINGS.telemetry_root_path}/{date_key}/{event_key}",
        "previous_date_key": date_key if previous_event_key is not None else latest_meta.get("previous_date_key"),
        "previous_event_key": previous_event_key or latest_meta.get("previous_event_key"),
        "previous_path": None
        if previous_event_key is None
        else f"{BACKEND_SETTINGS.telemetry_root_path}/{date_key}/{previous_event_key}",
        "previous_ts_device": previous_ts_device,
        "previous_ts_server": previous_ts_server,
        "delta_device_sec": delta_device_sec,
        "delta_server_sec": delta_server_sec,
        "expected_device_min_sec": expected_min,
        "expected_device_max_sec": expected_max,
        "expected_server_min_sec": expected_min,
        "expected_server_max_sec": expected_max,
        "device_in_expected_range": expected_min <= delta_device_sec <= expected_max,
        "server_in_expected_range": expected_min <= delta_server_sec <= expected_max,
        "primary_poll_after_sec": primary_poll_after_sec,
        "retry_after_no_change_sec": int(latest_meta.get("retry_after_no_change_sec") or 300),
        "record_sha256": latest_meta.get("record_sha256") or f"restore_{event_key}",
        "ts_device": int(latest_record["ts_device"]),
        "ts_server": int(latest_record["ts_server"]),
        "updated_at_utc": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _build_live_payload(*, live_root: dict[str, Any], latest_record: dict[str, Any], event_key: str) -> dict[str, Any]:
    payload = copy.deepcopy(live_root)
    payload["schema_version"] = 1
    sensors = payload.setdefault("sensors", {})
    sensors["npk"] = {
        **sensors.get("npk", {}),
        "n": latest_record["packet"]["npk_data"]["N"],
        "p": latest_record["packet"]["npk_data"]["P"],
        "k": latest_record["packet"]["npk_data"]["K"],
        "ec": latest_record["packet"]["npk_data"]["ec"],
        "ph": latest_record["packet"]["npk_data"]["ph"],
        "humidity_percent": latest_record["packet"]["npk_data"]["hum"],
        "temperature_c": latest_record["packet"]["npk_data"]["temp"],
        "sample_valid": True,
        "read_ok": True,
        "status": "ok",
        "ts_sample": int(latest_record["ts_device"]),
    }
    sensors["sht30"] = {
        **sensors.get("sht30", {}),
        "humidity_percent": latest_record["packet"]["sht30_data"]["sht_hum_pct"],
        "temperature_c": latest_record["packet"]["sht30_data"]["sht_temp_c"],
        "sample_valid": True,
        "read_ok": True,
        "status": "ok",
        "ts_sample": int(latest_record["ts_device"]),
    }
    payload.setdefault("meta", {})
    payload["meta"]["last_event_id"] = event_key
    payload["meta"]["last_seen_ts"] = int(latest_record["ts_device"])
    payload["meta"]["last_sync_ts"] = int(latest_record["ts_server"])
    payload.setdefault("health", {}).setdefault("overall", {})
    payload["health"]["overall"]["last_sync_ts"] = int(latest_record["ts_server"])
    payload["health"]["overall"]["online"] = True
    return payload


def _resolve_event_timestamp(*, event_key: str, record_payload: dict[str, Any]) -> int | None:
    candidates = (
        record_payload.get("ts_server"),
        record_payload.get("ts_sample"),
        record_payload.get("packet", {}).get("system_data", {}).get("sample_epoch_sec"),
        event_key,
    )
    for candidate in candidates:
        try:
            ts_value = int(candidate)
        except (TypeError, ValueError):
            continue
        if ts_value > 0:
            return ts_value
    return None


if __name__ == "__main__":
    main()
