from __future__ import annotations


V6_OUTPUT_DIRNAME = "V6"
V6_DATASET_VERSION = "2026-07-15.sequence-8h-v1"
V6_GAP_BREAK_SEC = 180 * 60
V6_CHUNK_HOURS = 8
V6_CHUNK_START_HOURS: tuple[int, ...] = (0, 8, 16)
V6_MIN_CHUNK_COVERAGE_RATIO = 0.75
V6_LOW_MOISTURE_ONSET_MIN_STEPS = 3
V6_THERMAL_VPD_THRESHOLD_KPA = 2.5
V6_RAPID_WETTING_DELTA_PP = 5.0
V6_EC_SHIFT_DELTA_Q = 0.95

V6_PRIMARY_FEATURE_COLUMNS: tuple[str, ...] = (
    "npk.soil_moisture_pct",
    "npk.soil_temp_c",
    "npk.ec",
    "sht.temp_c",
    "sht.humidity_pct",
    "derived.vpd_kpa",
    "sequence.observed_mask",
    "sequence.interpolated_mask",
    "sequence.missing_mask",
    "sequence.time_since_last_observation_sec",
)

V6_AUXILIARY_FEATURE_COLUMNS: tuple[str, ...] = (
    "npk.ph",
    "npk.n_proxy",
    "npk.p_proxy",
    "npk.k_proxy",
)

V6_REQUIRED_COLUMNS: tuple[str, ...] = (
    "record.id",
    "record.node_id",
    "record.ts_sample",
    "record.segment_id",
    "record.segment_index",
    "record.sample_time_local",
    "record.segment_expected_interval_sec",
    "npk.soil_moisture_pct",
    "npk.soil_temp_c",
    "npk.ec",
    "sht.temp_c",
    "sht.humidity_pct",
)

V6_OPTIONAL_AUDIT_COLUMNS: tuple[str, ...] = (
    "sht.valid",
    "npk.valid",
    "sht.read_ok",
    "npk.read_ok",
    "sht.sample_valid",
    "npk.sample_valid",
    "sht.fault",
    "npk.fault",
    "npk.protocol_fault",
    "record.gap_flag",
    "record.missing_slot_count",
    "delivery.is_buffered_replay",
    "delivery.fallback_used",
    "device.reset_or_power_on",
    "device.wake_reason",
    "network.gprs",
    "network.device_online",
)

V6_TRAIN_LABELS: tuple[str, ...] = (
    "normal",
    "persistent_low_relative_moisture_event",
    "unknown_environment_event",
)
