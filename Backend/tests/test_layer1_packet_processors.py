from __future__ import annotations

import unittest

from Backend.Core.layer1.processors.npk.canonical import extract_npk_fields
from Backend.Core.layer1.processors.sht30.canonical import extract_sht30_fields
from Backend.Core.layer1.processors.status import build_sensor_branch


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
            }
        )
        self.assertEqual(fields["npk.soil_temp_c"], 28.1)
        self.assertEqual(fields["npk.soil_moisture_pct"], 55.0)
        self.assertEqual(fields["npk.ph"], 6.4)
        self.assertEqual(fields["npk.ec"], 410.0)
        self.assertEqual(fields["npk.packet_present"], True)
        self.assertEqual(fields["npk.values_valid"], True)

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


if __name__ == "__main__":
    unittest.main()
