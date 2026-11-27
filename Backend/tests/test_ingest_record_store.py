"""Ingest raw record store (s4f): verbatim, content-addressed, immutable, deterministic."""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from agrifusion.ingest.record_store import (
    RecordStoreError,
    RecordStoreReader,
    RecordStoreWriter,
    encode_record,
)
from agrifusion.ingest.sources.firebase import FirebaseSourceAdapter
from agrifusion.settings.runtime import BackendSettings


def _record(trace: str = "firmware trace " * 100) -> dict:
    # Long strings and a ':' in the event key: the old Layer0 dropped >160-char logs.
    return {"sensor_record": {"soil": 42}, "system_record": {"debug_log": trace}, "sim_record": {}}


class RecordStoreTests(unittest.TestCase):
    def test_firebase_legacy_mode_returns_unmodified_telemetry(self) -> None:
        payload = {"2026-09-01": {"evt": {"system_record": {"debug_log": "full trace"}}}}

        class FirebaseClient:
            def pull_data(self, *, node_path: str):
                return payload

        settings = BackendSettings(project_root=Path(tempfile.gettempdir()), node_id="Node1")
        adapter = FirebaseSourceAdapter(FirebaseClient(), settings)
        adapter._mode = "legacy_paths"
        self.assertEqual(adapter.fetch_full_history_payload(), payload)

    def test_put_stores_verbatim_bytes_named_by_their_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = RecordStoreWriter(Path(temp_dir), node_slug="node1")
            record = _record()
            result = store.put(
                date_key="2026-09-01", event_key="0001:firmware", source_kind="telemetry",
                source_path="Node1/telemetry/2026-09-01/0001:firmware", record=record,
            )
            store.save_index()
            data = result.path.read_bytes()
            self.assertEqual(json.loads(data), record)
            self.assertEqual(data, encode_record(record))
            self.assertEqual(hashlib.sha256(data).hexdigest(), result.sha256)
            self.assertTrue(result.path.name.endswith(f"_{result.sha256}.json"))
            self.assertNotIn(":", result.path.name)
            text = data.decode("utf-8")
            self.assertNotIn("_utc", text)  # no run metadata inside record files

    def test_same_record_twice_is_a_no_op(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            kwargs = dict(date_key="2026-09-01", event_key="1", source_kind="telemetry",
                          source_path="Node1/telemetry/2026-09-01/1", record=_record())
            first = RecordStoreWriter(root, node_slug="node1")
            r1 = first.put(**kwargs)
            first.save_index()
            index_bytes = (root / "records" / "index.json").read_bytes()
            second = RecordStoreWriter(root, node_slug="node1")
            r2 = second.put(**kwargs)
            second.save_index()
            self.assertTrue(r1.new_file and r1.new_version)
            self.assertFalse(r2.new_file or r2.new_version)
            self.assertEqual((root / "records" / "index.json").read_bytes(), index_bytes)

    def test_new_version_keeps_old_file_and_telemetry_copy_wins(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = RecordStoreWriter(root, node_slug="node1")
            telemetry = store.put(date_key="2026-09-01", event_key="1", source_kind="telemetry",
                                  source_path="Node1/telemetry/2026-09-01/1", record=_record("a"))
            latest = store.put(date_key="2026-09-01", event_key="1", source_kind="latest",
                               source_path="Node1/latest", record=_record("b"))
            store.save_index()
            self.assertTrue(telemetry.path.exists() and latest.path.exists())
            current = list(RecordStoreReader(root).iter_current())
            self.assertEqual(len(current), 1)
            self.assertEqual(current[0].sha256, telemetry.sha256)
            self.assertEqual(current[0].source_kind, "telemetry")

    def test_only_latest_copy_is_used_when_no_telemetry_copy(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = RecordStoreWriter(root, node_slug="node1")
            store.put(date_key="2026-09-01", event_key="1", source_kind="latest",
                      source_path="Node1/telemetry/2026-09-01/1", record=_record("b"))
            store.save_index()
            (current,) = RecordStoreReader(root).iter_current()
            self.assertEqual(current.record, _record("b"))

    def test_tampered_file_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = RecordStoreWriter(root, node_slug="node1")
            kwargs = dict(date_key="2026-09-01", event_key="1", source_kind="telemetry",
                          source_path="p", record=_record())
            result = store.put(**kwargs)
            store.save_index()
            result.path.write_text("{}", encoding="utf-8")
            with self.assertRaises(RecordStoreError):
                list(RecordStoreReader(root).iter_current())
            with self.assertRaisesRegex(RecordStoreError, "collision"):
                RecordStoreWriter(root, node_slug="node1").put(**kwargs)

    def test_rejects_unknown_kind_and_bad_date(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = RecordStoreWriter(Path(temp_dir), node_slug="node1")
            with self.assertRaises(ValueError):
                store.put(date_key="2026-09-01", event_key="1", source_kind="x", source_path="p", record={})
            with self.assertRaises(ValueError):
                store.put(date_key="latest", event_key="1", source_kind="latest", source_path="p", record={})


if __name__ == "__main__":
    unittest.main()
