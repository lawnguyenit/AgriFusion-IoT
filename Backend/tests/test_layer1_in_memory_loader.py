from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from Backend.Config.storage import read_json
from Backend.Core.layer1.loaders import FirebaseSourceLoader
from Backend.Core.layer1.pipelines import PreprocessingPipeline


def _base_record(*, ts_sample: int, ts_server: int | None = None) -> dict:
    return {
        "ts_sample": ts_sample,
        "ts_server": ts_sample if ts_server is None else ts_server,
        "ts_device": ts_sample,
        "sample_time_reconstructed": False,
        "event_meta": {
            "wake_reason": "timer",
            "duration_ms": 1000,
        },
        "health": {
            "overall": {
                "online": True,
                "heap_free": 123456,
            }
        },
        "modules": {
            "sim": {
                "signal_dbm": -75,
                "gprs": True,
            }
        },
        "packet": {
            "system_data": {
                "sample_epoch_sec": ts_sample,
            }
        },
        "sensors": {},
    }


class Layer1InMemoryLoaderTests(unittest.TestCase):
    def test_pipeline_accepts_preloaded_source_loader(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_root = root / "Layer1"

            record = _base_record(ts_sample=1779087815)
            record["packet"]["sht30_data"] = {
                "sht_temp_c": 33.89,
                "sht_hum_pct": 75.71,
            }
            record["packet"]["npk_data"] = {
                "temp": 29.3,
                "hum": 64.5,
                "ph": 3,
                "ec": 469,
                "N": 59,
                "P": 183,
                "K": 176,
                "crc_ok": True,
                "frame_ok": True,
                "npk_signal_present": True,
                "npk_values_valid": True,
            }
            record["sensors"] = {
                "sht30": {"read_ok": True, "sample_valid": True, "status": "ok", "error_code": ""},
                "npk": {"read_ok": True, "sample_valid": True, "status": "ok", "error_code": ""},
            }

            source_loader = FirebaseSourceLoader.from_payloads(
                base_dir=root / "MissingLayer0",
                node_id="Node1",
                history_payload={"2026-05-18": {"1779087815": record}},
                latest_payload=record,
                latest_meta={
                    "latest_event_key": "1779087815",
                    "latest_date_key": "2026-05-18",
                    "latest_path": "Node1/telemetry/2026-05-18/1779087815",
                },
            )

            result = PreprocessingPipeline(
                base_dir=root / "MissingLayer0",
                output_root=output_root,
                source_loader=source_loader,
            ).run()

            self.assertEqual(result.canonical_record_count, 1)
            latest = read_json(output_root / "canonical" / "telemetry_latest.json", default={})
            self.assertEqual(latest["sht"]["temp_c"], 33.89)
            self.assertTrue(latest["npk"]["valid"])


if __name__ == "__main__":
    unittest.main()
