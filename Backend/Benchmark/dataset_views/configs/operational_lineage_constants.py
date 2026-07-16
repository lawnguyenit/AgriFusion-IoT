from __future__ import annotations

from Backend.Benchmark.dataset_views.contracts import CycleWindowHorizon, PreOnsetTargetHorizon
from Backend.Config.paths import BACKEND_PATHS


V3_FAMILY_VIEW_IDS: tuple[str, ...] = (
    "v3_direct",
    "v3_derived",
    "v3_independent",
    "v3_pre_onset",
)

V3_DEFAULT_VIEW_IDS: tuple[str, ...] = (
    "v3_direct",
    "v3_independent",
)

V3_LEGACY_EVENT_CSV_PATH = (
    BACKEND_PATHS.benchmark_dir / "benchmark_dataset" / "dataset" / "benchmark_input_labeled.csv"
)

V3_CONTINUITY_POLICY_VERSION = "segment_cadence_x2_5.v1"
V3_CONTINUITY_THRESHOLD_MULTIPLIER = 2.5
V3_BOUNDARY_RESET_COLUMNS: tuple[str, ...] = (
    "record.segment_boundary_before",
    "split.boundary_before",
)

V3_DIRECT_FLAG_FIELDS: tuple[str, ...] = (
    "delivery.is_buffered_replay",
    "delivery.fallback_used",
    "network.gprs",
    "network.device_online",
    "device.reset_or_power_on",
    "record.gap_flag",
    "sht.packet_present",
    "sht.read_ok",
    "sht.sample_valid",
    "npk.packet_present",
    "npk.read_ok",
    "npk.sample_valid",
    "npk.crc_ok",
    "npk.frame_ok",
    "npk.signal_present",
    "npk.values_valid",
)

V3_DIRECT_COUNT_FIELDS: tuple[str, ...] = (
    "record.missing_slot_count",
    "sht.retry_count",
    "npk.retry_count",
)

V3_DIRECT_CODE_FIELDS: tuple[str, ...] = (
    "delivery.buffer_reason",
    "device.wake_reason",
    "sht.error_code",
    "sht.status",
    "npk.error_code",
    "npk.error_code_raw",
    "npk.status",
)

V3_INDEPENDENT_CURRENT_FIELDS: tuple[str, ...] = (
    "record.upload_delay_sec",
    "record.timestamp_mismatch_sec",
    "network.signal_dbm",
    "device.cycle_duration_ms",
    "device.heap_free",
    "sht.read_elapsed_ms",
    "npk.read_duration_ms",
)

V3_DERIVED_CYCLE_HORIZONS: tuple[CycleWindowHorizon, ...] = (
    CycleWindowHorizon(name="3c", cycles=3, min_valid_observations=2),
    CycleWindowHorizon(name="6c", cycles=6, min_valid_observations=3),
    CycleWindowHorizon(name="12c", cycles=12, min_valid_observations=5),
)

V3_INDEPENDENT_CYCLE_HORIZONS: tuple[CycleWindowHorizon, ...] = (
    CycleWindowHorizon(name="3c", cycles=3, min_valid_observations=2, min_slope_observations=3),
    CycleWindowHorizon(name="6c", cycles=6, min_valid_observations=3, min_slope_observations=3),
    CycleWindowHorizon(name="12c", cycles=12, min_valid_observations=5, min_slope_observations=3),
)

V3_PRE_ONSET_TARGET_HORIZONS: tuple[PreOnsetTargetHorizon, ...] = (
    PreOnsetTargetHorizon(name="1c", cycles=1),
    PreOnsetTargetHorizon(name="3c", cycles=3),
    PreOnsetTargetHorizon(name="6c", cycles=6),
)

V3_TARGET_EVENT_FAMILIES: tuple[str, ...] = (
    "system_context",
    "sensor_fault_context",
)

V3_TARGET_BIG_LABEL_TO_FAMILY: dict[str, str] = {
    "system_timing": "system_context",
    "sensor_fault_anomaly": "sensor_fault_context",
}
