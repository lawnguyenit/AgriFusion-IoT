"""Golden test: synthetic Node2 JSON export -> Layer0 -> Layer1 canonical outputs.

To update the golden on purpose, see Backend/tests/golden/data_chain/README.md.
"""
from __future__ import annotations

import contextlib
import difflib
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from Backend.Config.runtime import BackendSettings
from Backend.tests.golden_chain_support import (
    EXPECTED_DIR,
    INPUT_EXPORT,
    NODE_ID,
    read_expected,
    run_chain,
    snapshot,
)

UPDATE_HINT = (
    "If this change is intended, regenerate the golden with "
    "`python Backend/tests/golden/data_chain/update_golden.py` and review the git diff "
    "(see Backend/tests/golden/data_chain/README.md)."
)


class GoldenDataChainTests(unittest.TestCase):
    maxDiff = None

    def _assert_matches_golden(self, actual: dict[str, str]) -> None:
        expected = read_expected()
        self.assertTrue(expected, f"golden folder is empty: {EXPECTED_DIR}")
        self.assertEqual(
            sorted(actual), sorted(expected), f"Golden file set differs. {UPDATE_HINT}"
        )
        for rel in sorted(expected):
            if actual[rel] != expected[rel]:
                diff = "\n".join(
                    list(
                        difflib.unified_diff(
                            expected[rel].splitlines(),
                            actual[rel].splitlines(),
                            "golden/" + rel,
                            "actual/" + rel,
                            lineterm="",
                            n=1,
                        )
                    )[:40]
                )
                self.fail(f"Golden mismatch in {rel}\n{diff}\n{UPDATE_HINT}")

    def test_in_process_chain_matches_golden(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_chain(Path(temp_dir))
            self._assert_matches_golden(snapshot(Path(temp_dir)))

    @unittest.skipUnless(
        importlib.util.find_spec("firebase_admin") is not None,
        "firebase_admin is not installed; Backend.main imports it even for --source json-export "
        "(pip install -r Backend/requirements.txt)",
    )
    def test_cli_json_export_matches_golden(self) -> None:
        """Same chain through `python -m Backend.main --source json-export ...`."""
        from Backend import main as backend_main
        from Backend.Navigation.Core.layer1.pipelines import preprocessing as preprocessing_module

        with tempfile.TemporaryDirectory() as temp_dir:
            settings = BackendSettings(backend_dir=Path(temp_dir))
            argv = [
                "Backend.main",
                "--source", "json-export",
                "--input-json", str(INPUT_EXPORT),
                "--node-id", NODE_ID,
                "--full-history",
            ]
            # Backend.main.run_layer1 does not pass output_root, so PreprocessingPipeline falls back
            # to its module-level BACKEND_SETTINGS (the real Backend/Output_data). Patch both so the
            # test never writes into the repo. (Production gap, reported separately.)
            with mock.patch.object(backend_main, "BACKEND_SETTINGS", settings), mock.patch.object(
                preprocessing_module, "BACKEND_SETTINGS", settings
            ), mock.patch("sys.argv", argv), contextlib.redirect_stdout(io.StringIO()):
                backend_main.main()
            self._assert_matches_golden(snapshot(Path(temp_dir)))

    def test_fixture_is_current(self) -> None:
        """input_export.json must equal the generator output (no hand edits)."""
        import json
        import sys

        golden_dir = str(INPUT_EXPORT.parent)
        sys.path.insert(0, golden_dir)
        try:
            import make_fixture
        finally:
            sys.path.remove(golden_dir)
        on_disk = json.loads(INPUT_EXPORT.read_text(encoding="utf-8"))
        self.assertEqual(on_disk, make_fixture.build())


if __name__ == "__main__":
    unittest.main()
