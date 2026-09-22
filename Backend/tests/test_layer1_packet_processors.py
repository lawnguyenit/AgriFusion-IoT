from __future__ import annotations

import unittest

from Backend.Navigation.Core.layer1.processors.npk.canonical import extract_npk_fields
from Backend.Navigation.Core.layer1.processors.sht30.canonical import extract_sht30_fields
from Backend.Navigation.Core.layer1.processors.status import build_sensor_branch


class Layer1PacketProcessorTests(unittest.TestCase):
    def test_extract_sht30_fields(self) -> None:
        fields = extract_sht30_fields(
            {
                "sht_temp_c": "31.5",
                "sht_hum_pct": "80.2",
                "sht_retry_count": "2",
                "sht_read_elapsed_ms": "17",
            }
        )
        self.assertEqual(fields["sht.temp_c"], 31.5)
        self.assertEqual(fields["sht.humidity_pct"], 80.2)
        self.assertEqual(fields["sht.retry_count"], 2)
        self.assertEqual(fields["sht.read_elapsed_ms"], 17)
        self.assertEqual(fields["sht.packet_present"], True)

    def test_extract_npk_fields(self) -> None:
        fields = extract_npk_fields(
            {
                "temp": "28.1",
                "hum": "55.0",
                "ph": "6.4",
                "ec": "410",
                "N": "40",
                "P": "25",
                "K": "33",
                "crc_ok": 1,
                "frame_ok": 1,
                "npk_signal_present": 1,
                "npk_values_valid": 1,
                "temp_value_valid": 1,
                "temp_source": "ds18b20",
                "hum_value_valid": 1,
                "hum_source": "soil_moisture_v1_2",
                "hum_calibration_status": "provisional_default",
                "hum_value_semantics": "relative_index_0_100_not_vwc",
                "hum_raw_adc": 2630,
                "ph_protocol_ok": 1,
                "ph_value_valid": 1,
                "ph_state": "valid",
                "ec_value_valid": 1,
                "ec_source": "npk_proxy_derived",
                "ec_measurement_kind": "derived_proxy",
                "N_value_valid": 1,
                "P_value_valid": 1,
                "K_value_valid": 1,
            }
        )
        self.assertEqual(fields["npk.soil_temp_c"], 28.1)
        self.assertEqual(fields["npk.soil_moisture_pct"], 55.0)
        self.assertEqual(fields["npk.ph"], 6.4)
        self.assertEqual(fields["npk.ec"], 410.0)
        self.assertEqual(fields["npk.packet_present"], True)
        self.assertEqual(fields["npk.values_valid"], True)
        self.assertEqual(fields["npk.soil_temp_valid"], True)
        self.assertEqual(fields["npk.soil_temp_source"], "ds18b20")
        self.assertEqual(fields["npk.soil_moisture_valid"], True)
        self.assertEqual(fields["npk.soil_moisture_source"], "soil_moisture_v1_2")
        self.assertEqual(fields["npk.soil_moisture_calibration_status"], "provisional_default")
        self.assertEqual(fields["npk.soil_moisture_raw_adc"], 2630)
        self.assertEqual(fields["npk.ph_protocol_ok"], True)
        self.assertEqual(fields["npk.ph_valid"], True)
        self.assertEqual(fields["npk.ph_status"], "valid")
        self.assertEqual(fields["npk.ec_measurement_kind"], "derived_proxy")

    def test_field_validity_survives_invalid_aggregate_ph(self) -> None:
        fields = extract_npk_fields(
            {
                "temp": 33.0,
                "hum": 100.0,
                "ph": None,
                "ec": 220,
                "N": 10,
                "P": 53,
                "K": 63,
                "npk_values_valid": 0,
                "temp_value_valid": 1,
                "temp_source": "ds18b20",
                "hum_value_valid": 1,
                "hum_source": "soil_moisture_v1_2",
                "ph_protocol_ok": 1,
                "ph_value_valid": 0,
                "ph_state": "frame_ok_value_invalid",
                "ec_value_valid": 1,
                "ec_measurement_kind": "derived_proxy",
                "N_value_valid": 1,
                "P_value_valid": 1,
                "K_value_valid": 1,
            }
        )
        self.assertTrue(fields["npk.soil_temp_valid"])
        self.assertTrue(fields["npk.soil_moisture_valid"])
        self.assertTrue(fields["npk.ec_valid"])
        self.assertTrue(fields["npk.ph_protocol_ok"])
        self.assertFalse(fields["npk.ph_valid"])
        self.assertEqual(fields["npk.ph_status"], "frame_ok_value_invalid")

    def test_build_sensor_branch(self) -> None:
        branch = build_sensor_branch(
            packet_present=True,
            sensor_status={
                "read_ok": True,
                "sample_valid": True,
                "status": "ok",
                "error_code": "",
            },
            normalized_prefix="npk",
            protocol_flags=(True, True, True, True),
        )
        self.assertEqual(branch["npk.valid"], True)
        self.assertEqual(branch["npk.fault"], False)
        self.assertEqual(branch["npk.protocol_fault"], False)
        self.assertEqual(branch["npk.error_class"], "ok")

    def test_error_class_keeps_sht_invalid_value_distinct_from_missing_packet(self) -> None:
        invalid = build_sensor_branch(
            packet_present=True,
            sensor_status={
                "read_ok": True,
                "sample_valid": False,
                "status": "error",
                "error_code": "measurement_invalid_zero_frame",
            },
            normalized_prefix="sht",
        )
        missing = build_sensor_branch(
            packet_present=False,
            sensor_status={},
            normalized_prefix="sht",
        )
        self.assertEqual(invalid["sht.error_class"], "value_invalid")
        self.assertEqual(missing["sht.error_class"], "missing_packet")


if __name__ == "__main__":
    unittest.main()
