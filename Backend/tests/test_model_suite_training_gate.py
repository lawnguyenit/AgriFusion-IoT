"""s5h: model_suite trains only on a runner contract marked validation_status=ready."""
from __future__ import annotations

import json
import tempfile
import unittest
import warnings
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pandas as pd

from agrifusion_research.core.evaluation_protocols.pipeline.build import TRAINING_READY_GATES, protocol_validation_status
from agrifusion_research.core.model_suite import gate
from agrifusion_research.core.model_suite.contracts.run_spec import ProtocolSourceRef
from agrifusion_research.core.model_suite.pipeline import orchestration
from agrifusion_research.core.model_suite.protocol_training.smoke import run_smoke_training


def _protocol_run(root: Path, status: str | None) -> Path:
    run_dir = root / "evaluation_protocols_test"
    (run_dir / "run_metadata").mkdir(parents=True)
    payload: dict[str, object] = {"validation_gates": {}}
    if status is not None:
        payload["validation_status"] = status
    (run_dir / "run_metadata" / "protocol_validation_report.json").write_text(json.dumps(payload), encoding="utf-8")
    return run_dir


class TrainingGateTests(unittest.TestCase):
    def test_ready_passes_without_override(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            record = gate.check_training_gate(_protocol_run(Path(temp), "ready"))
        self.assertEqual(record["validation_status"], "ready")
        self.assertFalse(record["override"])

    def test_blocked_missing_status_and_missing_report_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for status, sub in (("blocked", "a"), (None, "b")):
                with self.assertRaises(gate.UnauditedRunError):
                    gate.check_training_gate(_protocol_run(root / sub, status))
            with self.assertRaises(gate.UnauditedRunError):
                gate.check_training_gate(root / "does_not_exist")

    def test_override_is_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as temp, warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            record = gate.check_training_gate(_protocol_run(Path(temp), "blocked"), allow_unaudited=True)
        self.assertTrue(record["override"])
        self.assertEqual(record["validation_status"], "blocked")
        self.assertEqual(record["override_reason"], "--allow-unaudited")

    def test_evaluation_protocols_status_needs_every_training_gate(self) -> None:
        gates = {name: True for name in TRAINING_READY_GATES}
        self.assertEqual(protocol_validation_status(gates), "ready")
        gates["runner_assertions_passed"] = False
        self.assertEqual(protocol_validation_status(gates), "blocked")


class TrainingEntryPointsUseTheGateTests(unittest.TestCase):
    def test_smoke_training_refuses_before_touching_the_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run_dir = _protocol_run(Path(temp), "blocked")
            with self.assertRaises(gate.UnauditedRunError):
                run_smoke_training(run_dir)
            self.assertFalse((run_dir / "primary_protocol").exists())

    def test_smoke_suite_refuses_and_override_lands_in_run_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_dir = _protocol_run(root, "blocked")
            with self.assertRaises(gate.UnauditedRunError):
                orchestration.run_smoke_suite(protocol_run_dir=run_dir, model_keys=("dummy_majority",), show_progress=False)

            source = ProtocolSourceRef(run_dir, run_dir, run_dir, run_dir, run_dir, run_dir)
            empty = pd.DataFrame()
            with mock.patch.multiple(
                orchestration,
                assert_models_available=lambda keys: None,
                load_protocol_runner=lambda path: SimpleNamespace(source_ref=source),
                _default_artifact_root=lambda: root / "model_suite",
                load_stage_specs_for_profile=lambda path, name: (),
                build_pooled_prediction_summary=lambda frame: empty,
                build_model_comparison_table=lambda frame: empty,
                write_run_guides=lambda **kwargs: [],
                write_artifact_catalog=lambda *args, **kwargs: None,
            ), warnings.catch_warnings():
                warnings.simplefilter("ignore")
                orchestration.run_smoke_suite(
                    protocol_run_dir=run_dir,
                    model_keys=("dummy_majority",),
                    show_progress=False,
                    allow_unaudited=True,
                )
            manifests = list((root / "model_suite").rglob("run_manifest.json"))
            self.assertEqual(len(manifests), 1)
            recorded = json.loads(manifests[0].read_text(encoding="utf-8"))["metadata"]["training_gate"]
            self.assertTrue(recorded["override"])
            self.assertEqual(recorded["validation_status"], "blocked")


if __name__ == "__main__":
    unittest.main()
