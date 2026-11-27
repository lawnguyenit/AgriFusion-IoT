"""Golden test: synthetic Node2 JSON export -> Layer0 -> Layer1 canonical outputs.

To update the golden on purpose, see Backend/tests/golden/data_chain/README.md.
"""
from __future__ import annotations

import contextlib
import difflib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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

    def test_cli_json_export_matches_golden(self) -> None:
        """Same chain through `python -m Backend.main --source json-export ...`.

        Also guards GD1 bugs B2 (Layer1 ignored the configured output root) and B3
        (firebase_admin imported for json-export): the CLI writes only under
        AGRIFUSION_HOME and must not need firebase_admin.
        """
        from Backend import main as backend_main

        with tempfile.TemporaryDirectory() as temp_dir:
            argv = [
                "Backend.main",
                "--source", "json-export",
                "--input-json", str(INPUT_EXPORT),
                "--node-id", NODE_ID,
                "--full-history",
            ]
            with mock.patch.dict(os.environ, {"AGRIFUSION_HOME": temp_dir}), mock.patch(
                "sys.argv", argv
            ), contextlib.redirect_stdout(io.StringIO()):
                backend_main.main()
            self._assert_matches_golden(snapshot(Path(temp_dir)))

    def test_cli_json_export_runs_without_firebase_admin(self) -> None:
        import subprocess
        import sys

        code = (
            "import sys; sys.modules['firebase_admin'] = None; "
            "from Backend import main; main.main()"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            result = subprocess.run(
                [
                    sys.executable, "-c", code,
                    "--source", "json-export", "--input-json", str(INPUT_EXPORT),
                    "--node-id", NODE_ID, "--full-history",
                ],
                capture_output=True,
                text=True,
                env={**os.environ, "AGRIFUSION_HOME": temp_dir},
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Layer1 status: ok", result.stdout)

    def test_cli_only_layer1_reads_node_id_from_layer0_manifest(self) -> None:
        from Backend import main as backend_main

        with tempfile.TemporaryDirectory() as temp_dir:
            run_chain(Path(temp_dir))
            with mock.patch.dict(
                os.environ, {"AGRIFUSION_HOME": temp_dir, "EXPORT_NODE_ID": ""}
            ), mock.patch("sys.argv", ["Backend.main", "--only-layer1"]), contextlib.redirect_stdout(
                io.StringIO()
            ) as out:
                backend_main.main()
            self.assertIn("Node id from Layer0 manifest: Node2", out.getvalue())

    def test_cli_requires_node_id(self) -> None:
        from Backend import main as backend_main

        with tempfile.TemporaryDirectory() as temp_dir:
            argv = ["Backend.main", "--source", "json-export", "--input-json", str(INPUT_EXPORT)]
            env = {"AGRIFUSION_HOME": temp_dir}
            with mock.patch.dict(os.environ, env), mock.patch.dict(
                os.environ, {"EXPORT_NODE_ID": ""}
            ), mock.patch("sys.argv", argv), contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(ValueError, "node id is not configured"):
                    backend_main.main()

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
