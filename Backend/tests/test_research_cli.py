"""s5g: one CLI wraps every entry point; no sys.path hacks in the research package."""
from __future__ import annotations

import contextlib
import importlib
import io
import unittest
from pathlib import Path

from agrifusion_research import cli

OPTIONAL_DEPENDENCIES = {"torch", "xgboost", "pytabkit", "skorch"}  # research extras not always installed
PACKAGE = Path(__file__).resolve().parents[2] / "research" / "agrifusion_research"


class ResearchCliTests(unittest.TestCase):
    def test_every_command_runs_its_module_help(self) -> None:
        for words, module_name in cli.all_commands().items():
            with self.subTest(command=words):
                try:
                    module = importlib.import_module(module_name)
                except ModuleNotFoundError as exc:
                    if exc.name in OPTIONAL_DEPENDENCIES:
                        self.skipTest(f"{words}: optional dependency {exc.name} not installed")
                    raise
                self.assertTrue(callable(getattr(module, "main", None)))
                out = io.StringIO()
                code = 0
                with contextlib.redirect_stdout(out):
                    try:
                        cli.main([*words.split(), "--help"])
                    except SystemExit as stop:
                        code = stop.code
                self.assertEqual(code, 0)
                self.assertIn("usage:", out.getvalue())

    def test_every_script_entry_point_is_reachable_from_the_cli(self) -> None:
        reachable = set(cli.all_commands().values())
        scripts = {
            ".".join(("agrifusion_research", *path.relative_to(PACKAGE).with_suffix("").parts))
            for path in PACKAGE.rglob("*.py")
            if 'if __name__ == "__main__"' in path.read_text(encoding="utf-8")
            and path.name not in {"cli.py", "__main__.py"}
        }
        self.assertEqual(sorted(scripts - reachable), [])

    def test_unknown_command_exits_with_usage(self) -> None:
        with self.assertRaises(SystemExit) as stop:
            cli.main(["nope"])
        self.assertIn("unknown command", str(stop.exception.code))

    def test_no_sys_path_hacks(self) -> None:
        offending = [
            str(path.relative_to(PACKAGE)) for path in PACKAGE.rglob("*.py")
            if "sys.path" in path.read_text(encoding="utf-8")
        ]
        self.assertEqual(offending, [])


if __name__ == "__main__":
    unittest.main()
