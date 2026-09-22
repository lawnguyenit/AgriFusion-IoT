import unittest

import pandas as pd

from Backend.Benchmark.source_intake.adapter import (
    build_canonical_candidate,
    build_legacy_projection,
)
from Backend.Benchmark.source_intake.audit import build_audit


def _source_frame() -> pd.DataFrame:
    rows = []
    for index, ts in enumerate([1_000, 2_000, 3_000]):
        rows.append(
            {
                "node_id": "Node1",
                "raw_date_key": "2026-04-01",
                "event_key": 10_000 + index,
                "ts_sample": ts,
                "sample_time_local_iso": f"2026-04-01T00:{index * 16:02d}:00+07:00",
                "date_local": "2026-04-01",
                "time_reconstructed": False,
                "buffered": index == 2,
                "replayed": index == 2,
                "buffer_reason": None,
                "signal_dbm": -60,
                "pdp_active": True,
                "wake_reason": "timer",
                "cycle_duration_ms": 64,
                "air_temp_c": 30.0 + index,
                "air_rh_pct": 70.0,
                "air_read_ok": True,
                "air_sample_valid": True,
                "air_retry_count": 0,
                "air_error_code": None,
                "soil_moisture_pct": 60.0,
                "soil_moisture_valid": True,
                "soil_moisture_value_semantics": "legacy_percent_like_unverified",
                "soil_moisture_calibration_status": "legacy_unverified",
                "soil_moisture_source": "legacy_npk_data.hum",
                "soil_temp_c": 28.0,
                "soil_temp_valid": True,
                "soil_temp_source": "legacy_npk_data.temp",
                "soil_ec_us_cm": 500.0,
                "soil_ec_valid": True,
                "ec_measurement_kind": "legacy_unknown",
                "ec_source": "legacy_npk_data.ec",
                "soil_n_proxy": 60.0,
                "soil_p_proxy": 180.0,
                "soil_k_proxy": 170.0,
                "soil_ph": 6.0,
                "soil_ph_valid": True,
                "soil_read_ok": True,
                "soil_sample_valid": True,
                "soil_retry_count": 0,
                "soil_error_code": None,
                "ph_state": None,
                "delta_min": 16.6667,
                "gap_ratio": 1.1111,
                "gap_gt_30m": False,
                "gap_gt_60m": False,
                "duplicate_timestamp_flag": False,
                "export_key_corruption_flag": False,
            }
        )
    return pd.DataFrame(rows)


class SourceIntakeTests(unittest.TestCase):
    def test_candidate_uses_identity_key_but_does_not_fabricate_server_time(self):
        source = _source_frame()
        candidate = build_canonical_candidate(source)

        self.assertEqual(len(candidate), 3)
        self.assertEqual(candidate["record.id"].iloc[0], "Node1:2026-04-01:10000")
        self.assertTrue(candidate["record.ts_server"].isna().all())
        self.assertTrue(candidate["record.upload_time_local"].isna().all())
        self.assertEqual(candidate["record.segment_id"].nunique(), 1)
        self.assertEqual(candidate["record.delta_prev_sec"].iloc[1], 1000)

    def test_legacy_projection_preserves_requested_old_column_order(self):
        source = _source_frame()
        candidate = build_canonical_candidate(source)
        columns = ["record.id", "record.ts_sample", "sht.temp_c", "npk.ec"]
        projection = build_legacy_projection(candidate, columns)
        self.assertEqual(list(projection.columns), columns)
        self.assertEqual(projection.shape, (3, 4))

    def test_audit_reports_overlap_and_replay_sensor_rows(self):
        source = _source_frame()
        candidate = build_canonical_candidate(source)
        old = build_legacy_projection(candidate.iloc[:2].copy(), list(candidate.columns))
        summary, details = build_audit(source, old, candidate)

        self.assertEqual(summary["shared_key_count"], 2)
        self.assertEqual(summary["new_only_key_count"], 1)
        self.assertEqual(summary["buffered_or_replayed_rows"], 1)
        self.assertEqual(summary["replayed_rows_with_any_sensor_value"], 1)
        self.assertEqual(int(details["value_comparison"].query("source_column == 'ts_sample'")["mismatch_rows"].iloc[0]), 0)


if __name__ == "__main__":
    unittest.main()
