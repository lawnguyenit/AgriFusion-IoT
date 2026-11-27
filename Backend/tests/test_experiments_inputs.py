"""s5f: every experiment declares its run inputs in inputs.yaml; no run id is hard-coded in code."""
from __future__ import annotations

import argparse
import re
import tempfile
import unittest
from pathlib import Path

from agrifusion_research.core.common.paths import REPO_ROOT
from agrifusion_research.core.common.run_inputs import load_run_inputs, parse_with_run_inputs

PACKAGE = Path(__file__).resolve().parents[2] / "research" / "agrifusion_research"
TIMESTAMPED_RUN = re.compile(r"artifacts/[^\"'\s]*_20\d{6}")


class ExperimentInputsTests(unittest.TestCase):
    def test_every_experiment_has_a_valid_inputs_file(self) -> None:
        experiments = [p for p in (PACKAGE / "experiments").iterdir() if p.is_dir() and (p / "__init__.py").exists()]
        self.assertGreater(len(experiments), 5)
        for experiment in experiments:
            with self.subTest(experiment=experiment.name):
                load_run_inputs(experiment / "inputs.yaml")

    def test_no_timestamped_artifact_path_in_python_code(self) -> None:
        offending = [
            f"{path.relative_to(PACKAGE)}:{number}"
            for path in PACKAGE.rglob("*.py")
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
            if TIMESTAMPED_RUN.search(line)
        ]
        self.assertEqual(offending, [])

    def test_k_window_inputs_resolve_against_repo_root(self) -> None:
        inputs = load_run_inputs(PACKAGE / "experiments" / "k_window_variants" / "inputs.yaml")
        self.assertEqual(
            inputs.paths["protocol_run_dir"],
            REPO_ROOT / "output/research/evaluation_protocols/artifacts/evaluation_protocols_20260902_203645",
        )


class ParseWithRunInputsTests(unittest.TestCase):
    def _parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser()
        parser.add_argument("--run-dir", type=Path, default=None)
        return parser

    def test_missing_input_stops_the_command(self) -> None:
        with self.assertRaises(SystemExit):
            parse_with_run_inputs(self._parser(), ("run_dir",), argv=[])

    def test_file_fills_and_cli_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "inputs.yaml"
            path.write_text("inputs:\n  run_dir: output/x\n", encoding="utf-8")
            args = parse_with_run_inputs(self._parser(), ("run_dir",), argv=["--inputs", str(path)])
            self.assertEqual(args.run_dir, REPO_ROOT / "output/x")
            args = parse_with_run_inputs(self._parser(), ("run_dir",), argv=["--inputs", str(path), "--run-dir", "/abs"])
            self.assertEqual(args.run_dir, Path("/abs"))

    def test_unknown_top_level_key_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "inputs.yaml"
            path.write_text("input:\n  run_dir: x\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_run_inputs(path)


if __name__ == "__main__":
    unittest.main()
