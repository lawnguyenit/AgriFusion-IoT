from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from Backend.Config.runtime import BackendSettings
from Backend.Navigation.Core.layer0.sources.firebase import FirebaseSourceAdapter
from Backend.Navigation.Core.layer0.stores.telemetry_store import write_full_history_raw_snapshots


class Layer0RawHistoryTests(unittest.TestCase):
    def test_firebase_legacy_mode_exposes_unmodified_telemetry_for_raw_archive(self) -> None:
        payload = {"2026-09-01": {"evt": {"system_record": {"debug_log": "full trace"}}}}

        class FirebaseClient:
            def pull_data(self, *, node_path: str):
                return payload

        settings = BackendSettings(backend_dir=Path(tempfile.gettempdir()), node_id="Node1")
        adapter = FirebaseSourceAdapter(FirebaseClient(), settings)
        adapter._mode = "legacy_paths"

        self.assertEqual(adapter.fetch_full_history_raw_payload(), payload)

    def test_raw_history_preserves_long_firmware_evidence_without_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = BackendSettings(backend_dir=Path(temp_dir), node_id="Node1")
            payload = {
                "2026-09-01": {
                "0001:firmware": {
                        "sensor_record": {"soil": 42},
                        "system_record": {"debug_log": "firmware trace " * 100},
                    }
                }
            }
            checked_at = datetime(2026, 9, 29, tzinfo=timezone.utc)

            first_count = write_full_history_raw_snapshots(
                settings=settings,
                telemetry_payload=payload,
                checked_at=checked_at,
            )
            raw_files = [
                path for path in settings.firebase_raw_history_root.rglob("*.json")
                if "archive_runs" not in path.parts
            ]
            stored = json.loads(raw_files[0].read_text(encoding="utf-8"))
            original_bytes = raw_files[0].read_bytes()
            second_count = write_full_history_raw_snapshots(
                settings=settings,
                telemetry_payload=payload,
                checked_at=datetime(2026, 9, 30, tzinfo=timezone.utc),
            )

            self.assertEqual(first_count, 1)
            self.assertEqual(second_count, 0)
            self.assertEqual(len(raw_files), 1)
            self.assertEqual(stored["record"]["system_record"]["debug_log"], "firmware trace " * 100)
            self.assertEqual(raw_files[0].read_bytes(), original_bytes)
            self.assertRegex(raw_files[0].name, r"_[0-9a-f]{64}\.json$")
            self.assertNotIn(":", raw_files[0].name)
            manifests = sorted((settings.firebase_raw_history_root / "archive_runs").glob("*.json"))
            self.assertEqual(len(manifests), 2)
            latest_manifest = json.loads(manifests[-1].read_text(encoding="utf-8"))
            self.assertEqual(latest_manifest["completion_status"], "complete")
            self.assertEqual(latest_manifest["eligible_record_count"], 1)
            self.assertEqual(latest_manifest["existing_verified_record_file_count"], 1)
            stored["record"]["system_record"]["debug_log"] = "tampered"
            raw_files[0].write_text(json.dumps(stored), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Content-addressed raw history collision"):
                write_full_history_raw_snapshots(
                    settings=settings,
                    telemetry_payload=payload,
                    checked_at=checked_at,
                )


if __name__ == "__main__":
    unittest.main()
