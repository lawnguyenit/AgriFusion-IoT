from __future__ import annotations

from typing import Any

try:
    from Config.runtime import BACKEND_SETTINGS
except ModuleNotFoundError:
    from ....Config.runtime import BACKEND_SETTINGS

from ...utils.common import format_local_iso, safe_int
from ..contracts import SourceRecord
from .common import (
    as_dict,
    as_optional_bool,
    first_non_empty_str,
    first_bool,
    first_not_none,
    normalize_buffer_reason,
    normalize_text,
)


def extract_raw_buffer_reason(source_record: SourceRecord) -> str | None:
    payload = source_record.payload
    system_record = as_dict(payload.get("system_record"))
    system_sync = as_dict(system_record.get("sync"))
    return first_non_empty_str(
        payload.get("buffer_reason"),
        system_sync.get("buffer_reason_code"),
    )


def build_record_and_context_fields(source_record: SourceRecord) -> dict[str, Any]:
    payload = source_record.payload
    packet = as_dict(payload.get("packet"))
    packet_system = as_dict(packet.get("system_data"))
    event_meta = as_dict(payload.get("event_meta"))
    health = as_dict(payload.get("health"))
    overall_health = as_dict(health.get("overall"))
    modules = as_dict(payload.get("modules"))
    sim_module = as_dict(modules.get("sim"))
    system_record = as_dict(payload.get("system_record"))
    system_identity = as_dict(system_record.get("identity"))
    system_time = as_dict(system_record.get("time"))
    system_sync = as_dict(system_record.get("sync"))
    system_cycle = as_dict(system_record.get("cycle"))
    system_health = as_dict(system_record.get("device_health"))
    sim_record = as_dict(payload.get("sim_record"))
    sim_network = as_dict(sim_record.get("network"))

    ts_sample = safe_int(payload.get("ts_sample"))
    ts_server = safe_int(payload.get("ts_server"))
    ts_device = safe_int(payload.get("ts_device"))
    packet_system_sample_epoch = safe_int(packet_system.get("sample_epoch_sec"))

    if ts_server is None:
        ts_server = safe_int(system_time.get("ts_server"))
    if ts_sample is None:
        ts_sample = safe_int(system_time.get("ts_sample"))
    if ts_device is None:
        ts_device = packet_system_sample_epoch

    node_id = str(
        system_identity.get("node_id")
        or source_record.source_path.split("/")[0]
        or BACKEND_SETTINGS.node_id
    )
    sample_time_reconstructed = first_bool(
        payload.get("sample_time_reconstructed"),
        packet_system.get("sample_time_reconstructed"),
        system_time.get("time_reconstructed"),
    )
    sample_time_local = first_non_empty_str(
        payload.get("sample_time_local"),
        payload.get("upload_time_local"),
        format_local_iso(ts_sample, BACKEND_SETTINGS.timezone),
    )
    upload_time_local = first_non_empty_str(
        payload.get("upload_time_local"),
        format_local_iso(ts_server, BACKEND_SETTINGS.timezone),
    )

    replayed_raw = first_bool(payload.get("replayed"), system_sync.get("replayed"))
    buffered_raw = first_bool(payload.get("was_buffered"), system_sync.get("buffered"))
    is_buffered_replay = True if replayed_raw is True or buffered_raw is True else False
    fallback_used = as_optional_bool(payload.get("fallback_used"))
    buffer_reason = normalize_buffer_reason(extract_raw_buffer_reason(source_record))
    buffered_at_ms = safe_int(payload.get("buffered_at_ms"))
    replayed_at_ms = safe_int(payload.get("replayed_at_ms"))
    metadata_complete = bool(
        is_buffered_replay
        and buffer_reason is not None
        and buffered_at_ms is not None
        and replayed_at_ms is not None
    )

    wake_reason = normalize_text(
        first_non_empty_str(
            event_meta.get("wake_reason"),
            system_cycle.get("wake_reason"),
        )
    )
    reset_or_power_on = wake_reason == "power_on_or_reset"
    is_demo = bool(payload.get("demo_template_name")) or bool(
        payload.get("demo_template_id")
    ) or bool(system_record.get("synthetic"))

    return {
        "record.node_id": node_id,
        "record.date_key": source_record.date_key,
        "record.event_key": source_record.event_key,
        "record.id": f"{node_id}:{source_record.date_key}:{source_record.event_key}",
        "record.source_path": source_record.source_path,
        "record.source_kind": source_record.source_kind,
        "record.ts_sample": ts_sample,
        "record.ts_server": ts_server,
        "record.ts_device": ts_device,
        "record.sample_time_reconstructed": sample_time_reconstructed,
        "record.sample_time_local": sample_time_local,
        "record.upload_time_local": upload_time_local,
        "record.timestamp_mismatch_sec": None
        if packet_system_sample_epoch is None or ts_sample is None
        else packet_system_sample_epoch - ts_sample,
        "record.hour_sin": None,
        "record.hour_cos": None,
        "record.segment_id": None,
        "record.segment_index": None,
        "record.segment_boundary_before": None,
        "record.segment_expected_interval_sec": None,
        "record.delta_prev_sec": None,
        "record.upload_delay_sec": None,
        "record.gap_flag": None,
        "record.missing_slot_count": None,
        "record.is_demo": is_demo,
        "record.excluded_reason": None,
        "delivery.replayed_raw": replayed_raw,
        "delivery.was_buffered_raw": buffered_raw,
        "delivery.is_buffered_replay": is_buffered_replay,
        "delivery.fallback_used": fallback_used,
        "delivery.buffer_reason": buffer_reason,
        "delivery.buffered_at_ms": buffered_at_ms,
        "delivery.replayed_at_ms": replayed_at_ms,
        "delivery.metadata_complete": metadata_complete,
        "network.signal_dbm": safe_int(
            first_not_none(sim_module.get("signal_dbm"), sim_network.get("signal_dbm"))
        ),
        "network.gprs": first_bool(sim_module.get("gprs"), sim_network.get("pdp_active")),
        "network.device_online": as_optional_bool(overall_health.get("online")),
        "device.wake_reason": wake_reason,
        "device.cycle_duration_ms": safe_int(
            first_not_none(event_meta.get("duration_ms"), system_cycle.get("cycle_duration_ms"))
        ),
        "device.heap_free": safe_int(
            first_not_none(overall_health.get("heap_free"), system_health.get("heap_free"))
        ),
        "device.reset_or_power_on": reset_or_power_on,
    }
