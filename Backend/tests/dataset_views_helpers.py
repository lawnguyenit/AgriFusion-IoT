from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def create_dataset_views_fixture(root: Path) -> dict[str, Path]:
    canonical_df = pd.DataFrame(
        [
            {
                "record.id": "r1",
                "record.node_id": "Node1",
                "record.date_key": "2026-07-01",
                "record.event_key": "1001",
                "record.source_path": "Node1/telemetry/2026-07-01/1001",
                "record.source_kind": "history",
                "record.ts_sample": 1000,
                "record.ts_server": 1075,
                "record.ts_device": 995,
                "record.sample_time_reconstructed": False,
                "record.sample_time_local": "2026-07-01T07:16:40+07:00",
                "record.upload_time_local": "2026-07-01T07:18:00+07:00",
                "record.timestamp_mismatch_sec": 80,
                "record.hour_sin": 0.2,
                "record.hour_cos": 0.9,
                "record.segment_id": "node1_seg_0001",
                "record.segment_index": 1,
                "record.segment_boundary_before": True,
                "record.segment_expected_interval_sec": 1000,
                "record.delta_prev_sec": pd.NA,
                "record.upload_delay_sec": 75,
                "record.gap_flag": False,
                "record.missing_slot_count": 0,
                "record.is_demo": False,
                "record.excluded_reason": pd.NA,
                "sht.temp_c": 28.4,
                "sht.humidity_pct": 71.2,
                "sht.packet_present": True,
                "sht.retry_count": 0,
                "sht.read_elapsed_ms": 12.0,
                "npk.soil_temp_c": 27.1,
                "npk.soil_moisture_pct": 63.5,
                "npk.ph": 6.8,
                "npk.ec": 1.9,
                "npk.n_proxy": 12.0,
                "npk.p_proxy": 22.0,
                "npk.k_proxy": 32.0,
                "npk.packet_present": True,
                "npk.error_code_raw": 0,
                "npk.crc_ok": True,
                "npk.frame_ok": True,
                "npk.signal_present": True,
                "npk.values_valid": True,
                "npk.retry_count": 0,
                "npk.consecutive_fail_count": 0,
                "npk.read_duration_ms": 48.0,
                "sht.read_ok": True,
                "sht.sample_valid": True,
                "sht.status": "ok",
                "sht.error_code": "0",
                "sht.valid": True,
                "sht.fault": False,
                "sht.missing_packet": False,
                "npk.read_ok": True,
                "npk.sample_valid": True,
                "npk.status": "ok",
                "npk.error_code": "0",
                "npk.valid": True,
                "npk.fault": False,
                "npk.missing_packet": False,
                "npk.protocol_fault": False,
            },
            {
                "record.id": "r2",
                "record.node_id": "Node1",
                "record.date_key": "2026-07-01",
                "record.event_key": "1002",
                "record.source_path": "Node1/telemetry/2026-07-01/1002",
                "record.source_kind": "history",
                "record.ts_sample": 2000,
                "record.ts_server": 2080,
                "record.ts_device": 1995,
                "record.sample_time_reconstructed": False,
                "record.sample_time_local": "2026-07-01T07:33:20+07:00",
                "record.upload_time_local": "2026-07-01T07:34:37+07:00",
                "record.timestamp_mismatch_sec": 85,
                "record.hour_sin": 0.3,
                "record.hour_cos": 0.8,
                "record.segment_id": "node1_seg_0001",
                "record.segment_index": 1,
                "record.segment_boundary_before": False,
                "record.segment_expected_interval_sec": 1000,
                "record.delta_prev_sec": 1000,
                "record.upload_delay_sec": 77,
                "record.gap_flag": False,
                "record.missing_slot_count": 0,
                "record.is_demo": False,
                "record.excluded_reason": pd.NA,
                "sht.temp_c": 28.7,
                "sht.humidity_pct": 72.4,
                "sht.packet_present": True,
                "sht.retry_count": 1,
                "sht.read_elapsed_ms": 13.5,
                "npk.soil_temp_c": 27.4,
                "npk.soil_moisture_pct": 64.0,
                "npk.ph": 6.9,
                "npk.ec": pd.NA,
                "npk.n_proxy": 13.0,
                "npk.p_proxy": 23.0,
                "npk.k_proxy": 33.0,
                "npk.packet_present": True,
                "npk.error_code_raw": 4,
                "npk.crc_ok": False,
                "npk.frame_ok": True,
                "npk.signal_present": True,
                "npk.values_valid": False,
                "npk.retry_count": 2,
                "npk.consecutive_fail_count": 1,
                "npk.read_duration_ms": 51.0,
                "sht.read_ok": True,
                "sht.sample_valid": True,
                "sht.status": "ok",
                "sht.error_code": "0",
                "sht.valid": True,
                "sht.fault": False,
                "sht.missing_packet": False,
                "npk.read_ok": False,
                "npk.sample_valid": False,
                "npk.status": "warn",
                "npk.error_code": "4",
                "npk.valid": False,
                "npk.fault": True,
                "npk.missing_packet": False,
                "npk.protocol_fault": True,
            },
            {
                "record.id": "r3",
                "record.node_id": "Node1",
                "record.date_key": "2026-07-01",
                "record.event_key": "1003",
                "record.source_path": "Node1/telemetry/2026-07-01/1003",
                "record.source_kind": "history",
                "record.ts_sample": 3000,
                "record.ts_server": 3090,
                "record.ts_device": 2990,
                "record.sample_time_reconstructed": False,
                "record.sample_time_local": "2026-07-01T07:50:00+07:00",
                "record.upload_time_local": "2026-07-01T07:51:25+07:00",
                "record.timestamp_mismatch_sec": 100,
                "record.hour_sin": 0.4,
                "record.hour_cos": 0.7,
                "record.segment_id": "node1_seg_0001",
                "record.segment_index": 1,
                "record.segment_boundary_before": False,
                "record.segment_expected_interval_sec": 1000,
                "record.delta_prev_sec": 1000,
                "record.upload_delay_sec": 85,
                "record.gap_flag": True,
                "record.missing_slot_count": 1,
                "record.is_demo": False,
                "record.excluded_reason": pd.NA,
                "sht.temp_c": 29.0,
                "sht.humidity_pct": 73.1,
                "sht.packet_present": False,
                "sht.retry_count": 2,
                "sht.read_elapsed_ms": 17.5,
                "npk.soil_temp_c": 27.8,
                "npk.soil_moisture_pct": 65.2,
                "npk.ph": 7.0,
                "npk.ec": 2.1,
                "npk.n_proxy": 14.0,
                "npk.p_proxy": 24.0,
                "npk.k_proxy": 34.0,
                "npk.packet_present": False,
                "npk.error_code_raw": 9,
                "npk.crc_ok": False,
                "npk.frame_ok": False,
                "npk.signal_present": False,
                "npk.values_valid": False,
                "npk.retry_count": 3,
                "npk.consecutive_fail_count": 2,
                "npk.read_duration_ms": 59.0,
                "sht.read_ok": False,
                "sht.sample_valid": False,
                "sht.status": "fault",
                "sht.error_code": "7",
                "sht.valid": False,
                "sht.fault": True,
                "sht.missing_packet": True,
                "npk.read_ok": False,
                "npk.sample_valid": False,
                "npk.status": "fault",
                "npk.error_code": "9",
                "npk.valid": False,
                "npk.fault": True,
                "npk.missing_packet": True,
                "npk.protocol_fault": True,
            },
        ]
    ).convert_dtypes()

    catalog_rows = []
    for column in canonical_df.columns:
        feature_role = "audit_only"
        rule_proxy_level = "none"
        split_only = False
        allowed_views = ""
        forbidden_views = ""
        used_by_label_rule = False
        eligible_for_model = False

        if column.startswith("record."):
            feature_role = "split_and_order" if column in {"record.ts_sample"} else "audit_only"
            split_only = column in {"record.ts_sample"}
        elif column in {"sht.temp_c", "sht.humidity_pct", "npk.soil_temp_c", "npk.soil_moisture_pct", "npk.ec"}:
            feature_role = "measurement"
            allowed_views = "v0|v1"
            eligible_for_model = True
        elif column in {"npk.ph", "npk.n_proxy", "npk.p_proxy", "npk.k_proxy"}:
            feature_role = "measurement"
            allowed_views = "v1"
            eligible_for_model = True
        elif column in {
            "sht.packet_present",
            "sht.read_ok",
            "sht.sample_valid",
            "sht.retry_count",
            "sht.read_elapsed_ms",
            "npk.packet_present",
            "npk.read_ok",
            "npk.sample_valid",
            "npk.error_code_raw",
            "npk.crc_ok",
            "npk.frame_ok",
            "npk.signal_present",
            "npk.values_valid",
            "npk.retry_count",
            "npk.consecutive_fail_count",
            "npk.read_duration_ms",
        }:
            feature_role = "sensor_context"
            allowed_views = "v1"
            eligible_for_model = True
            if column in {
                "sht.packet_present",
                "sht.read_ok",
                "sht.sample_valid",
                "npk.packet_present",
                "npk.read_ok",
                "npk.sample_valid",
                "npk.error_code_raw",
                "npk.crc_ok",
                "npk.frame_ok",
                "npk.signal_present",
                "npk.values_valid",
            }:
                used_by_label_rule = True
                rule_proxy_level = "direct"
        elif column in {
            "sht.status",
            "sht.error_code",
            "sht.valid",
            "sht.fault",
            "sht.missing_packet",
            "npk.status",
            "npk.error_code",
            "npk.valid",
            "npk.fault",
            "npk.missing_packet",
            "npk.protocol_fault",
        }:
            feature_role = "rule_proxy"
            used_by_label_rule = True
            rule_proxy_level = "direct" if column.endswith(("status", "error_code")) else "derived"

        catalog_rows.append(
            {
                "canonical_name": column,
                "feature_role": feature_role,
                "used_by_label_rule": used_by_label_rule,
                "rule_proxy_level": rule_proxy_level,
                "split_only": split_only,
                "allowed_views": allowed_views,
                "forbidden_views": forbidden_views,
                "eligible_for_model": eligible_for_model,
            }
        )

    catalog_df = pd.DataFrame(catalog_rows).convert_dtypes()
    labels_df = pd.DataFrame(
        [
            {"record.id": "r1", "label_binary": 0},
            {"record.id": "r2", "label_binary": 1},
            {"record.id": "r3", "label_binary": 1},
        ]
    ).convert_dtypes()

    canonical_path = root / "telemetry_history.csv"
    catalog_path = root / "feature_catalog.csv"
    manifest_path = root / "manifest.json"
    labels_path = root / "labels.parquet"

    canonical_df.to_csv(canonical_path, index=False)
    catalog_df.to_csv(catalog_path, index=False)
    manifest_path.write_text(
        json.dumps(
            {
                "pipeline": "layer1_canonical_preprocessing",
                "canonical_record_count": int(len(canonical_df)),
                "output_paths": {"canonical_history_path": str(canonical_path)},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    labels_df.to_parquet(labels_path, index=False)

    return {
        "canonical_path": canonical_path,
        "catalog_path": catalog_path,
        "manifest_path": manifest_path,
        "labels_path": labels_path,
    }


def create_dataset_views_v2_fixture(root: Path) -> dict[str, Path]:
    rows: list[dict[str, object]] = []
    physical_order = 0

    logical_chunk_a = [
        _build_v2_row(index=i, ts_sample=1000 + i * 900, segment_id="node1_seg_0001", segment_index=1)
        for i in range(30)
    ]
    logical_chunk_a[8]["npk.valid"] = False
    logical_chunk_a[8]["npk.ec"] = 999.0
    logical_chunk_a[8]["npk.ph"] = 999.0
    logical_chunk_a[8]["npk.n_proxy"] = 999.0
    logical_chunk_a[8]["npk.p_proxy"] = 999.0
    logical_chunk_a[8]["npk.k_proxy"] = 999.0

    replay_row = logical_chunk_a.pop(6)
    replay_row["delivery.is_buffered_replay"] = True
    replay_row["record.ts_server"] = int(replay_row["record.ts_sample"]) + 7200
    replay_row["record.upload_time_local"] = "2026-07-01T09:00:00+07:00"

    ordered_rows = logical_chunk_a[:10] + [replay_row] + logical_chunk_a[10:]
    for row in ordered_rows:
        row["record.source_path"] = f"Node1/telemetry/{row['record.date_key']}/{row['record.event_key']}"
        row["record.source_kind"] = "history"
        row["record.segment_boundary_before"] = bool(row["record.segment_boundary_before"])
        row["split.boundary_before"] = False
        row["_physical_order"] = physical_order
        rows.append(row)
        physical_order += 1

    gap_start = int(ordered_rows[-1]["record.ts_sample"]) + 4000
    for offset in range(10):
        row = _build_v2_row(
            index=100 + offset,
            ts_sample=gap_start + offset * 900,
            segment_id="node1_seg_0001",
            segment_index=1,
        )
        row["record.segment_boundary_before"] = False
        row["split.boundary_before"] = offset == 3
        row["_physical_order"] = physical_order
        rows.append(row)
        physical_order += 1

    segment2_start = gap_start + 10 * 900 + 900
    for offset in range(6):
        row = _build_v2_row(
            index=200 + offset,
            ts_sample=segment2_start + offset * 900,
            segment_id="node1_seg_0002",
            segment_index=2,
        )
        row["record.segment_boundary_before"] = offset == 0
        row["split.boundary_before"] = False
        row["_physical_order"] = physical_order
        rows.append(row)
        physical_order += 1

    canonical_df = pd.DataFrame(rows).sort_values("_physical_order", kind="stable").drop(columns=["_physical_order"])
    canonical_df = canonical_df.convert_dtypes()

    catalog_df = _build_dataset_views_catalog(canonical_df)
    labels_df = pd.DataFrame(
        [{"record.id": record_id, "label_binary": int(index % 2)} for index, record_id in enumerate(canonical_df["record.id"])]
    ).convert_dtypes()
    segment_manifest = {
        "schema_version": 1,
        "generated_at_utc": "2026-07-14T00:00:00Z",
        "segment_count": 2,
        "segments": [
            _build_segment_manifest_entry(canonical_df, segment_id="node1_seg_0001", expected_interval_sec=900),
            _build_segment_manifest_entry(canonical_df, segment_id="node1_seg_0002", expected_interval_sec=900),
        ],
    }
    return _write_dataset_views_fixture_files(
        root=root,
        canonical_df=canonical_df,
        catalog_df=catalog_df,
        labels_df=labels_df,
        segment_manifest=segment_manifest,
    )


def _build_v2_row(index: int, ts_sample: int, segment_id: str, segment_index: int) -> dict[str, object]:
    date_key = "2026-07-01"
    event_key = str(1000 + index)
    base = float(index)
    return {
        "record.id": f"r{index}",
        "record.node_id": "Node1",
        "record.date_key": date_key,
        "record.event_key": event_key,
        "record.source_path": f"Node1/telemetry/{date_key}/{event_key}",
        "record.source_kind": "history",
        "record.ts_sample": ts_sample,
        "record.ts_server": ts_sample + 70,
        "record.ts_device": ts_sample - 5,
        "record.sample_time_reconstructed": False,
        "record.sample_time_local": "2026-07-01T07:00:00+07:00",
        "record.upload_time_local": "2026-07-01T07:01:10+07:00",
        "record.timestamp_mismatch_sec": 75,
        "record.hour_sin": 0.1,
        "record.hour_cos": 0.9,
        "record.segment_id": segment_id,
        "record.segment_index": segment_index,
        "record.segment_boundary_before": index in {0, 200},
        "record.segment_expected_interval_sec": 900,
        "record.delta_prev_sec": pd.NA,
        "record.upload_delay_sec": 70,
        "record.gap_flag": False,
        "record.missing_slot_count": 0,
        "record.is_demo": False,
        "record.excluded_reason": pd.NA,
        "split.boundary_before": False,
        "delivery.is_buffered_replay": False,
        "sht.temp_c": 20.0 + base,
        "sht.humidity_pct": 60.0 + base,
        "npk.soil_temp_c": 25.0 + base / 2.0,
        "npk.soil_moisture_pct": 50.0 + base,
        "npk.ec": 1.0 + base / 10.0,
        "npk.ph": 6.5 + base / 100.0,
        "npk.n_proxy": 10.0 + base,
        "npk.p_proxy": 20.0 + base,
        "npk.k_proxy": 30.0 + base,
        "sht.packet_present": True,
        "sht.retry_count": 0,
        "sht.read_elapsed_ms": 12.0,
        "npk.packet_present": True,
        "npk.error_code_raw": 0,
        "npk.crc_ok": True,
        "npk.frame_ok": True,
        "npk.signal_present": True,
        "npk.values_valid": True,
        "npk.retry_count": 0,
        "npk.consecutive_fail_count": 0,
        "npk.read_duration_ms": 45.0,
        "sht.read_ok": True,
        "sht.sample_valid": True,
        "sht.status": "ok",
        "sht.error_code": "0",
        "sht.valid": True,
        "sht.fault": False,
        "sht.missing_packet": False,
        "npk.read_ok": True,
        "npk.sample_valid": True,
        "npk.status": "ok",
        "npk.error_code": "0",
        "npk.valid": True,
        "npk.fault": False,
        "npk.missing_packet": False,
        "npk.protocol_fault": False,
    }


def _build_dataset_views_catalog(canonical_df: pd.DataFrame) -> pd.DataFrame:
    minimal_measurements = {
        "sht.temp_c",
        "sht.humidity_pct",
        "npk.soil_temp_c",
        "npk.soil_moisture_pct",
        "npk.ec",
    }
    full_measurements = minimal_measurements | {"npk.ph", "npk.n_proxy", "npk.p_proxy", "npk.k_proxy"}
    diagnostic_fields = {
        "sht.packet_present",
        "sht.read_ok",
        "sht.sample_valid",
        "sht.retry_count",
        "sht.read_elapsed_ms",
        "npk.packet_present",
        "npk.read_ok",
        "npk.sample_valid",
        "npk.error_code_raw",
        "npk.crc_ok",
        "npk.frame_ok",
        "npk.signal_present",
        "npk.values_valid",
        "npk.retry_count",
        "npk.consecutive_fail_count",
        "npk.read_duration_ms",
    }
    proxy_fields = {
        "sht.status",
        "sht.error_code",
        "sht.valid",
        "sht.fault",
        "sht.missing_packet",
        "npk.status",
        "npk.error_code",
        "npk.valid",
        "npk.fault",
        "npk.missing_packet",
        "npk.protocol_fault",
        "delivery.is_buffered_replay",
    }

    rows: list[dict[str, object]] = []
    for column in canonical_df.columns:
        feature_role = "audit_only"
        used_by_label_rule = False
        rule_proxy_level = "none"
        split_only = False
        allowed_views = ""
        forbidden_views = ""
        eligible_for_model = False

        if column == "record.ts_sample":
            feature_role = "split_and_order"
            split_only = True
        elif column.startswith("record.") or column == "split.boundary_before":
            feature_role = "audit_only"
        elif column in minimal_measurements:
            feature_role = "measurement"
            allowed_views = "v0|v1|v2"
            eligible_for_model = True
        elif column in full_measurements:
            feature_role = "measurement"
            allowed_views = "v1|v2"
            eligible_for_model = True
        elif column in diagnostic_fields:
            feature_role = "sensor_context"
            allowed_views = "v1"
            eligible_for_model = True
        elif column in proxy_fields:
            feature_role = "rule_proxy"
            used_by_label_rule = True
            rule_proxy_level = "direct" if column.endswith(("status", "error_code")) or column == "delivery.is_buffered_replay" else "derived"

        rows.append(
            {
                "canonical_name": column,
                "feature_role": feature_role,
                "used_by_label_rule": used_by_label_rule,
                "rule_proxy_level": rule_proxy_level,
                "split_only": split_only,
                "allowed_views": allowed_views,
                "forbidden_views": forbidden_views,
                "eligible_for_model": eligible_for_model,
            }
        )
    return pd.DataFrame(rows).convert_dtypes()


def _build_segment_manifest_entry(
    canonical_df: pd.DataFrame,
    segment_id: str,
    expected_interval_sec: int,
) -> dict[str, object]:
    segment_df = canonical_df.loc[canonical_df["record.segment_id"] == segment_id].copy()
    segment_df = segment_df.sort_values("record.ts_sample", kind="stable").reset_index(drop=True)
    return {
        "node_id": str(segment_df.loc[0, "record.node_id"]),
        "segment_id": segment_id,
        "segment_index": int(segment_df.loc[0, "record.segment_index"]),
        "row_count": int(len(segment_df)),
        "start_ts_sample": int(segment_df.loc[0, "record.ts_sample"]),
        "end_ts_sample": int(segment_df.loc[len(segment_df) - 1, "record.ts_sample"]),
        "start_record_id": str(segment_df.loc[0, "record.id"]),
        "end_record_id": str(segment_df.loc[len(segment_df) - 1, "record.id"]),
        "expected_interval_sec": expected_interval_sec,
        "canonical_format": "csv_fixture",
        "history_path": str((canonical_df.index.name or "telemetry_history.csv")),
        "latest_path": "telemetry_latest.json",
        "views_root": "views",
    }


def _write_dataset_views_fixture_files(
    root: Path,
    canonical_df: pd.DataFrame,
    catalog_df: pd.DataFrame,
    labels_df: pd.DataFrame,
    segment_manifest: dict[str, object],
) -> dict[str, Path]:
    canonical_path = root / "telemetry_history.csv"
    catalog_path = root / "feature_catalog.csv"
    manifest_path = root / "manifest.json"
    segment_manifest_path = root / "segments_manifest.json"
    labels_path = root / "labels.parquet"

    canonical_df.to_csv(canonical_path, index=False)
    catalog_df.to_csv(catalog_path, index=False)
    segment_manifest_path.write_text(json.dumps(segment_manifest, indent=2) + "\n", encoding="utf-8")
    manifest_path.write_text(
        json.dumps(
            {
                "pipeline": "layer1_canonical_preprocessing",
                "canonical_record_count": int(len(canonical_df)),
                "output_paths": {
                    "canonical_history_path": str(canonical_path),
                    "feature_catalog_path": str(catalog_path),
                    "segment_manifest_path": str(segment_manifest_path),
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    labels_df.to_parquet(labels_path, index=False)

    return {
        "canonical_path": canonical_path,
        "catalog_path": catalog_path,
        "manifest_path": manifest_path,
        "segment_manifest_path": segment_manifest_path,
        "labels_path": labels_path,
    }
