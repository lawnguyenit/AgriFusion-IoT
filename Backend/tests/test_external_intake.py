from __future__ import annotations

import json
import hashlib
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from Backend.Benchmark.external_intake.adapters.stuard import build_stuard_candidate
from Backend.Benchmark.external_intake.adapters.uci import build_uci_candidate
from Backend.Benchmark.external_intake.pipeline import ExternalIntakeConfig, run_external_intake


class ExternalIntakeTests(unittest.TestCase):
    def test_uci_adapter_separates_criteria_and_preserves_row_level_audit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "uci.csv"
            source.write_text(
                "Date;Time;CO(GT);PT08.S1(CO);NOx(GT);PT08.S3(NOx);T;RH;AH\n"
                "01/01/2004;00.00.00;1,2;100;-200;50;10,0;20,0;1,0\n"
                "bad-date;bad-time;2,0;110;3;55;11,0;21,0;1,1\n"
                "01/01/2004;01.00.00;-200;120;4;60;12,0;22,0;1,2\n",
                encoding="utf-8",
            )

            candidate, excluded, audit = build_uci_candidate(source)

        self.assertEqual(len(candidate), 2)
        self.assertEqual(len(excluded), 1)
        self.assertEqual(candidate.loc[0, "criterion.co_gt_mg_m3"], 1.2)
        self.assertTrue(pd.isna(candidate.loc[0, "criterion.nox_gt_ppb"]))
        self.assertEqual(candidate.loc[1, "sensor.co"], 120)
        self.assertEqual(audit["target_sensor_columns"], {"co": "sensor.co", "nox": "sensor.nox"})
        self.assertIn("criterion.co_gt_mg_m3", audit["forbidden_model_columns"])
        self.assertFalse(audit["data_semantics"]["independent_criterion"])
        self.assertEqual(
            audit["data_semantics"]["target_defining_reference_measurements"],
            ["criterion.co_gt_mg_m3", "criterion.nox_gt_ppb"],
        )
        self.assertIn("does not mean", audit["data_semantics"]["legacy_role_interpretation"])
        self.assertEqual(audit["timestamp_time_basis"], "local_wall_time_no_timezone_in_source")

    def test_stuard_joins_only_prior_water_and_environment_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_csv(
                root / "stuard_environmental_data.csv",
                "id,device_identifier,ts_generation,co2,humidity,pressure,temperature,battery\n"
                "1,env,1704102960000,400,60,1010,22,90\n"  # 09:56 UTC
                "2,env,1704103440000,401,61,1010,23,90\n",  # 10:04 UTC
            )
            self._write_csv(
                root / "stuard_soil_data.csv",
                "id,device_identifier,ts_generation,line,electrical_conductivity,humidity,temperature,battery\n"
                "1,soil,1704103200000,1,100,35,20,80\n",  # 10:00 UTC
            )
            self._write_csv(
                root / "stuard_water_meter_data.csv",
                "id,ts_generation,device_identifier,line,current_volume\n"
                "1,1704103020000,water,1,10.0\n"  # 09:57 UTC
                "2,1704103380000,water,1,11.0\n",  # 10:03 UTC
            )

            adapted = build_stuard_candidate(root)

        row = adapted.canonical.iloc[0]
        self.assertEqual(row["water_volume_m3"], 10.0)
        self.assertEqual(row["air_temperature_c"], 22)
        self.assertEqual(row["water_alignment_age_sec"], 180.0)
        self.assertEqual(row["environment_alignment_age_sec"], 240.0)
        self.assertEqual(adapted.audit["water_future_matches"], 0)
        self.assertEqual(adapted.audit["environment_future_matches"], 0)

    def test_stuard_excludes_repeated_stream_headers_but_rejects_unknown_lines(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_csv(
                root / "stuard_environmental_data.csv",
                "id,device_identifier,ts_generation,co2,humidity,pressure,temperature,battery\n"
                "id,device_identifier,ts_generation,co2,humidity,pressure,temperature,battery\n"
                "1,env,1704102960000,400,60,1010,22,90\n",
            )
            self._write_csv(
                root / "stuard_soil_data.csv",
                "id,device_identifier,ts_generation,line,electrical_conductivity,humidity,temperature,battery\n"
                "id,device_identifier,ts_generation,line,electrical_conductivity,humidity,temperature,battery\n"
                "1,soil,1704103200000,1,100,35,20,80\n",
            )
            self._write_csv(
                root / "stuard_water_meter_data.csv",
                "id,ts_generation,device_identifier,line,current_volume\n"
                "id,ts_generation,device_identifier,line,current_volume\n"
                "1,1704103020000,water,1,10.0\n",
            )
            adapted = build_stuard_candidate(root)

        self.assertEqual(len(adapted.canonical), 1)
        self.assertEqual(len(adapted.excluded), 3)
        self.assertTrue(adapted.excluded["exclusion_reason"].eq("REPEATED_HEADER").all())

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_csv(
                root / "stuard_environmental_data.csv",
                "id,device_identifier,ts_generation,co2,humidity,pressure,temperature,battery\n"
                "1,env,1704102960000,400,60,1010,22,90\n",
            )
            self._write_csv(
                root / "stuard_soil_data.csv",
                "id,device_identifier,ts_generation,line,electrical_conductivity,humidity,temperature,battery\n"
                "1,soil,1704103200000,99,100,35,20,80\n",
            )
            self._write_csv(
                root / "stuard_water_meter_data.csv",
                "id,ts_generation,device_identifier,line,current_volume\n"
                "1,1704103020000,water,1,10.0\n",
            )
            with self.assertRaisesRegex(ValueError, "only lines 1, 2, and 3"):
                build_stuard_candidate(root)

    def test_pipeline_keeps_raw_release_separate_from_timestamped_processing_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_dir = root / "input"
            input_dir.mkdir()
            self._write_csv(
                input_dir / "stuard_environmental_data.csv",
                "id,device_identifier,ts_generation,co2,humidity,pressure,temperature,battery\n"
                "1,env,1704102960000,400,60,1010,22,90\n",
            )
            self._write_csv(
                input_dir / "stuard_soil_data.csv",
                "id,device_identifier,ts_generation,line,electrical_conductivity,humidity,temperature,battery\n"
                "1,soil,1704103200000,1,100,35,20,80\n",
            )
            self._write_csv(
                input_dir / "stuard_water_meter_data.csv",
                "id,ts_generation,device_identifier,line,current_volume\n"
                "1,1704103020000,water,1,10.0\n",
            )

            result = run_external_intake(
                ExternalIntakeConfig(
                    dataset_id="stuard_tomato_irrigation_2023",
                    input_dir=input_dir,
                    raw_root=root / "Output_data" / "raw",
                    processed_root=root / "Output_data" / "processed",
                    release_id="source_2023",
                )
            )
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(result.row_count, 1)
            self.assertEqual(result.raw_dir.parent.name, "stuard_tomato_irrigation_2023")
            self.assertEqual(result.output_dir.parent.name, "stuard_tomato_irrigation_2023")
            self.assertTrue((result.raw_dir / "stuard_soil_data.csv").is_file())
            self.assertTrue((result.raw_dir / "raw_manifest.json").is_file())
            self.assertTrue(result.canonical_path.is_file())
            raw_manifest = json.loads((result.raw_dir / "raw_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(raw_manifest["source_files"][0]["origin_kind"], "local_copy")
            self.assertEqual(raw_manifest["source_files"][0]["origin_locator"], str((input_dir / "stuard_environmental_data.csv").resolve()))
            self.assertEqual(
                manifest["raw_manifest_sha256"],
                hashlib.sha256((result.raw_dir / "raw_manifest.json").read_bytes()).hexdigest(),
            )
            self.assertEqual(manifest["target_generation"], "not_performed")
            self.assertEqual(manifest["feature_materialization"], "not_performed")

    @staticmethod
    def _write_csv(path: Path, content: str) -> None:
        path.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
