from __future__ import annotations

import unittest

from Backend.Navigation.Core.layer0.sources.base import NormalizedSnapshotMixin


class Layer0SensorDiagnosticsTests(unittest.TestCase):
    def test_v2_npk_projection_promotes_semantic_provenance_without_raw_maps(self) -> None:
        payload = {
            "sensor_type": "soil_multi_sensor",
            "values": {
                "soil_temp_c": 33.0,
                "soil_moisture_pct": 100.0,
                "soil_ph": None,
                "soil_ec_us_cm": 220,
                "soil_n_proxy": 10,
                "soil_p_proxy": 53,
                "soil_k_proxy": 63,
            },
            "read_status": {
                "read_ok": True,
                "sample_valid": False,
                "frame_ok": True,
                "crc_ok": True,
                "error_code": "ok",
                "field_validity": {"temp": False, "hum": False, "ph": True, "ec": True},
                "field_value_validity": {"temp": True, "hum": True, "ph": False, "ec": True},
                "field_source": {
                    "temp": "ds18b20",
                    "hum": "soil_moisture_v1_2",
                    "ph": "modbus_register",
                    "ec": "npk_proxy_derived",
                },
                "ph_state": "frame_ok_value_invalid",
                "ec_measurement_kind": "derived_proxy",
                "moisture_calibration": {
                    "status": "provisional_default",
                    "profile": "manufacturer_example_scaled_12bit_direction_adjusted",
                    "value_semantics": "relative_index_0_100_not_vwc",
                    "latest_raw_adc": 2630,
                    "latest_voltage_mv": 2240,
                    "install_depth_cm_min": 10.0,
                    "install_depth_cm_max": 15.0,
                },
            },
        }

        legacy = NormalizedSnapshotMixin._build_legacy_npk_packet(
            object(), "soil_7in1_01", payload
        )

        self.assertEqual(legacy["temp_source"], "ds18b20")
        self.assertTrue(legacy["hum_value_valid"])
        self.assertEqual(legacy["hum_calibration_status"], "provisional_default")
        self.assertEqual(legacy["hum_raw_adc"], 2630)
        self.assertEqual(legacy["ph_state"], "frame_ok_value_invalid")
        self.assertEqual(legacy["ec_measurement_kind"], "derived_proxy")

    def test_sht_zero_frame_keeps_observed_values_and_error_trace(self) -> None:
        payload = {
            "sensor_type": "air_temp_humidity",
            "read_status": {
                "read_ok": True,
                "sample_valid": False,
                "value_valid": False,
                "values_available": True,
                "error_code": "measurement_invalid_zero_frame",
                "frame_ok": True,
                "temp_crc_ok": True,
                "hum_crc_ok": True,
                "raw_temp": 0,
                "raw_hum": 0,
                "observed_temp_c": -45.0,
                "observed_hum_pct": 0.0,
            },
            "values": {"air_temp_c": None, "air_rh_pct": None},
        }

        legacy = NormalizedSnapshotMixin._build_legacy_sht30_packet(
            object(), "air_sht30_01", payload
        )
        trace = NormalizedSnapshotMixin._build_sensor_trace_payload(
            object(),
            sensor_id="air_sht30_01",
            sensor_type="air_temp_humidity",
            read_status=payload["read_status"],
        )

        self.assertIsNone(legacy["sht_temp_c"])
        self.assertIsNone(legacy["sht_hum_pct"])
        self.assertEqual(legacy["sht_observed_temp_c"], -45.0)
        self.assertEqual(legacy["sht_observed_hum_pct"], 0.0)
        self.assertEqual(legacy["sht_error"], "measurement_invalid_zero_frame")
        self.assertTrue(legacy["sht_frame_ok"])
        self.assertEqual(trace["status"], "error")
        self.assertEqual(trace["error_code"], "measurement_invalid_zero_frame")


if __name__ == "__main__":
    unittest.main()
