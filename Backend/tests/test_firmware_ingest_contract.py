"""Contract firmware -> ingest -> canonical (s4g), plus ingest determinism.

Fixture: Backend/tests/fixtures/firmware_contract.py (records in the shape the firmware
publishes, derived from RawTelemetryReporter / FirebasePipeline / NodeRuntimePublisher).
"""
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from agrifusion.canonical import PreprocessingPipeline
from agrifusion.ingest import Layer0IngestionPipeline
from agrifusion.ingest.record_store import RecordStoreReader, encode_record
from agrifusion.settings.runtime import BackendSettings

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "firmware_contract.py"
_spec = importlib.util.spec_from_file_location("firmware_contract", _FIXTURE)
fw = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(fw)


def _all_telemetry(snapshot: dict) -> dict[tuple[str, str], dict]:
    return {(d, e): rec for d, day in snapshot["telemetry"].items() for e, rec in day.items()}


def _record_files(root: Path) -> dict[str, bytes]:
    base = root / "output" / "Layer0" / "Firebase_data"
    files = {p.relative_to(base).as_posix(): p.read_bytes() for p in (base / "records").rglob("*") if p.is_file()}
    files["new_raw/latest.json"] = (base / "new_raw" / "latest.json").read_bytes()
    return files


class FakeFirebase:
    """Production RTDB mode: the firmware writes latest/meta, so ingest uses legacy_paths."""

    def __init__(self, snapshot: dict):
        self.paths = {
            f"{fw.NODE_ID}/latest/meta": snapshot["latest"]["meta"],
            f"{fw.NODE_ID}/latest/current": snapshot["latest"]["current"],
            f"{fw.NODE_ID}/telemetry": snapshot["telemetry"],
        }

    def pull_data(self, *, node_path: str):
        return json.loads(json.dumps(self.paths.get(node_path)))


class FirmwareIngestContractTests(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls) -> None:
        cls.snapshot = fw.build_node_snapshot()

    def _run_json_export(self, root: Path) -> BackendSettings:
        export = root / "export.json"
        export.write_text(json.dumps(self.snapshot), encoding="utf-8")
        settings = BackendSettings(project_root=root, source_type="json-export",
                                   input_json_path=export, node_id=fw.NODE_ID)
        Layer0IngestionPipeline(settings=settings).run(full_history=True)
        return settings

    def _canonical(self, settings: BackendSettings) -> pd.DataFrame:
        result = PreprocessingPipeline(settings).run()
        self.assertEqual(result.status, "ok")
        return pd.read_parquet(result.canonical_history_path).set_index("record.event_key")

    # --- ingest keeps the firmware records verbatim ---------------------------------

    def test_fixture_covers_firmware_cases(self) -> None:
        records = list(_all_telemetry(self.snapshot).values())
        syncs = [r["system_record"]["sync"] for r in records]
        self.assertTrue(any(s["replayed"] for s in syncs))
        self.assertTrue(any(r["system_record"]["time"]["time_reconstructed"] for r in records))
        self.assertTrue(any(not r["sensor_record"]["air_sht30_01"]["read_status"]["sample_valid"] for r in records))
        self.assertTrue(any(not r["sensor_record"]["soil_7in1_01"]["read_status"]["read_ok"] for r in records))
        # latest/current differs from its telemetry copy (written after publishRecord)
        latest = self.snapshot["latest"]["current"]
        key = (fw.date_key(latest["system_record"]["time"]["ts_sample"]), latest["system_record"]["identity"]["record_id"])
        self.assertNotEqual(_all_telemetry(self.snapshot)[key], latest)

    def test_json_export_stores_every_record_verbatim(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = self._run_json_export(Path(temp_dir))
            stored = {(r.date_key, r.event_key): r for r in RecordStoreReader(settings.firebase_layer0_root).iter_current()}
            expected = _all_telemetry(self.snapshot)
            self.assertEqual(set(stored), set(expected))
            for key, record in expected.items():
                self.assertEqual(stored[key].record, record, key)
                self.assertEqual(stored[key].source_kind, "telemetry")
                self.assertEqual(stored[key].source_path, f"{fw.TELEMETRY_ROOT}/{key[0]}/{key[1]}")
            latest_bytes = settings.latest_payload_path.read_bytes()
            self.assertEqual(json.loads(latest_bytes), self.snapshot["latest"]["current"])
            self.assertEqual(latest_bytes, encode_record(self.snapshot["latest"]["current"]))
            # both versions of the latest event are kept as evidence
            index = json.loads((settings.firebase_layer0_root / "records" / "index.json").read_text())
            latest_id = self.snapshot["latest"]["current"]["system_record"]["identity"]["record_id"]
            (entry,) = [v for k, v in index["records"].items() if k.endswith("/" + latest_id)]
            self.assertEqual(sorted(v["source_kind"] for v in entry["versions"]), ["latest", "telemetry"])

    def test_firebase_production_mode_stores_the_same_records(self) -> None:
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            self._run_json_export(Path(a))
            settings = BackendSettings(project_root=Path(b), source_type="firebase", node_id=fw.NODE_ID)
            Layer0IngestionPipeline(FakeFirebase(self.snapshot), settings=settings).run(full_history=True)
            self.assertEqual(_record_files(Path(a)), _record_files(Path(b)))

    # --- canonical reads them ------------------------------------------------------

    def test_canonical_columns_from_firmware_records(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            df = self._canonical(self._run_json_export(Path(temp_dir)))
        self.assertEqual(len(df), 5)
        ok, sht_err, npk_err, replay, last = (str(fw.T0 + i * fw.INTERVAL_SEC) for i in range(5))
        replay = str(fw.T0 + 3 * fw.INTERVAL_SEC + 7)

        row = df.loc[ok]
        self.assertEqual(row["record.node_id"], "Node2")
        self.assertEqual(row["record.ts_sample"], fw.T0)
        self.assertEqual(row["sht.temp_c"], 27.0)
        self.assertEqual(row["npk.ph"], 6.3)
        self.assertEqual(row["npk.n_proxy"], 30)
        self.assertEqual(row["npk.ec_measurement_kind"], "derived_proxy")
        self.assertEqual(row["network.signal_dbm"], -79)
        self.assertEqual(row["network.operator"], "Viettel")
        self.assertTrue(row["device.reset_or_power_on"])
        self.assertTrue(row["sht.valid"])
        self.assertTrue(row["npk.valid"])
        self.assertFalse(row["delivery.is_buffered_replay"])

        row = df.loc[sht_err]
        self.assertTrue(pd.isna(row["sht.temp_c"]))
        self.assertTrue(row["sht.fault"])
        self.assertEqual(row["sht.error_class"], "value_invalid")
        self.assertTrue(row["sht.values_recorded_with_error"])
        self.assertTrue(row["npk.valid"])

        row = df.loc[npk_err]
        self.assertTrue(pd.isna(row["npk.ph"]))
        self.assertTrue(row["npk.fault"])
        self.assertEqual(row["npk.error_class"], "transport")
        self.assertEqual(row["npk.error_code_raw"], 226)
        self.assertEqual(row["npk.soil_temp_source"], "ds18b20")  # from field_source map
        self.assertFalse(row["npk.ph_valid"])
        self.assertTrue(row["sht.valid"])

        row = df.loc[replay]
        self.assertTrue(row["delivery.replayed_raw"])
        self.assertTrue(row["delivery.is_buffered_replay"])
        self.assertTrue(row["record.sample_time_reconstructed"])
        self.assertEqual(row["record.ts_sample"], fw.T0 + 3 * fw.INTERVAL_SEC + 7)

        self.assertEqual(df.loc[last, "record.source_kind"], "latest")
        self.assertEqual(df.loc[ok, "record.source_kind"], "history")

    def test_firebase_production_mode_gives_the_same_canonical_rows(self) -> None:
        """Regression for B13: in legacy_paths mode history/ was raw v2 and canonical
        lost every sensor value. Now both modes go through the same adapter."""
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            json_df = self._canonical(self._run_json_export(Path(a)))
            settings = BackendSettings(project_root=Path(b), source_type="firebase", node_id=fw.NODE_ID)
            Layer0IngestionPipeline(FakeFirebase(self.snapshot), settings=settings).run(full_history=True)
            fb_df = self._canonical(settings)
        self.assertEqual(fb_df["sht.temp_c"].notna().sum(), 4)
        pd.testing.assert_frame_equal(json_df, fb_df)

    @unittest.expectedFailure
    def test_known_gap_compact_npk_metadata_reaches_canonical(self) -> None:
        """B17 (pre-existing, not fixed here: it would change canonical values). For valid
        reads the firmware writes compact keys (soil_temp_source, ph_valid, n_proxy_valid,
        soil_moisture_calibration_status, ...) but the adapter only reads the field maps
        or temp_source/ph_value_valid/N_value_valid/hum_calibration_status, so these
        canonical columns are null. Remove expectedFailure when the adapter is fixed."""
        with tempfile.TemporaryDirectory() as temp_dir:
            row = self._canonical(self._run_json_export(Path(temp_dir))).loc[str(fw.T0)]
        self.assertEqual(row["npk.soil_temp_source"], "ds18b20")
        self.assertTrue(row["npk.ph_valid"])
        self.assertEqual(row["npk.soil_moisture_calibration_status"], "provisional_default")

    # --- determinism -----------------------------------------------------------------

    def test_same_input_gives_byte_identical_record_files(self) -> None:
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            self._run_json_export(Path(a))
            self._run_json_export(Path(b))
            first = _record_files(Path(a))
            self.assertEqual(first, _record_files(Path(b)))
            self._run_json_export(Path(a))  # second run into the same store
            self.assertEqual(first, _record_files(Path(a)))
            runs = list((Path(a) / "output" / "Layer0" / "Firebase_data" / "runs").glob("*.json"))
            self.assertEqual(len(runs), 2)  # run metadata goes to separate run manifests


if __name__ == "__main__":
    unittest.main()
