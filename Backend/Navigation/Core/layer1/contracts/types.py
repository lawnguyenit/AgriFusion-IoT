from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SourceRecord:
    source_name: str
    event_key: str
    date_key: str
    source_kind: str
    source_path: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class Layer1Result:
    status: str
    processed_source_records: int
    filtered_out_records: int
    total_new_snapshots: int
    output_root: Path
    manifest_path: Path
    sensor_counts: dict[str, int]
    canonical_record_count: int
    excluded_record_count: int
    demo_record_count: int
    canonical_history_path: Path
    canonical_latest_path: Path


@dataclass(frozen=True)
class TemporalSettings:
    expected_interval_sec: int = 900
    gap_threshold_sec: int = 3600
    segment_break_threshold_sec: int = 24 * 3600


@dataclass
class Layer1BuildStats:
    input_record_count: int = 0
    demo_record_count: int = 0
    excluded_record_count: int = 0
    canonical_record_count: int = 0
    duplicate_record_id_count: int = 0
    timestamp_parse_error_count: int = 0
    sht_packet_missing_count: int = 0
    npk_packet_missing_count: int = 0
    sht_fault_count: int = 0
    npk_fault_count: int = 0
    buffered_replay_count: int = 0
    fallback_count: int = 0
    reset_or_power_on_count: int = 0
    segment_count: int = 0
    buffer_reason_audit_row_count: int = 0
    warnings: list[str] = field(default_factory=list)
