"""Architecture test: no new import edge between top-level Backend packages.

Allow-list: Backend/tests/architecture/allowed_import_edges.txt (nodes: see architecture_graph.py)
Graph builder: Backend/tests/architecture_graph.py
"""
from __future__ import annotations

import unittest
import warnings
from pathlib import Path

from Backend.tests.architecture_graph import AGRIFUSION_NODES, REPO_ROOT, build_edges, mutual_pairs

RESEARCH_NODE_PREFIXES = ("research", "core", "external", "experiments")
ALLOWLIST = Path(__file__).resolve().parent / "architecture" / "allowed_import_edges.txt"
REGENERATE = "python Backend/tests/architecture/update_allowlist.py"


def load_allowlist(path: Path = ALLOWLIST) -> dict[tuple[str, str], str]:
    allowed: dict[tuple[str, str], str] = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        body, _, comment = line.partition("#")
        parts = [part.strip() for part in body.split("->")]
        if len(parts) != 2 or not all(parts):
            raise ValueError(f"{path.name}:{number}: expected '<src> -> <dst>', got {raw!r}")
        allowed[(parts[0], parts[1])] = comment.strip()
    return allowed


def diff_edges(
    actual: dict[tuple[str, str], list[str]], allowed: dict[tuple[str, str], str]
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    new = sorted(set(actual) - set(allowed))
    stale = sorted(set(allowed) - set(actual))
    return new, stale


class ArchitectureImportGraphTests(unittest.TestCase):
    def test_no_new_import_edges(self) -> None:
        actual = build_edges()
        allowed = load_allowlist()
        new, stale = diff_edges(actual, allowed)
        if stale:
            warnings.warn(
                "Allow-list lists edges that no longer exist (delete them): "
                + ", ".join(f"{s} -> {d}" for s, d in stale)
            )
        if new:
            details = "\n".join(
                f"  {src} -> {dst}   e.g. {actual[(src, dst)][0]}" for src, dst in new
            )
            self.fail(
                "New import edge(s) between top-level packages:\n"
                f"{details}\n"
                "If intentional, add them to Backend/tests/architecture/allowed_import_edges.txt "
                f"(`{REGENERATE}`) and justify it in the commit."
            )

    def test_cycles_are_documented_in_allowlist(self) -> None:
        """Every mutual import pair must be allow-listed with a 'to remove in <stage>' comment."""
        actual = build_edges()
        allowed = load_allowlist()
        undocumented = []
        for a, b in mutual_pairs(set(actual)):
            for edge in ((a, b), (b, a)):
                if "to remove in" not in allowed.get(edge, ""):
                    undocumented.append(f"{edge[0]} -> {edge[1]}")
        self.assertEqual(undocumented, [], "Cycle edges need a '# ... to remove in <stage>' comment")

    def test_no_import_cycles(self) -> None:
        """s5d removed the last cycle (evaluation_protocols <-> model_suite); keep it that way."""
        self.assertEqual(mutual_pairs(set(build_edges())), [])

    def test_evaluation_protocols_does_not_import_model_suite(self) -> None:
        """evaluation_protocols defines protocol/fold contracts; model fitting lives in model_suite."""
        self.assertNotIn(("core.evaluation_protocols", "core.model_suite"), set(build_edges()))

    def test_graph_detects_a_new_edge(self) -> None:
        """Guard the guard: the comparison reports an edge missing from the allow-list."""
        actual = {("ingest", "core.model_suite"): ["x.py:1"], **{e: ["y.py:1"] for e in load_allowlist()}}
        new, stale = diff_edges(actual, load_allowlist())
        self.assertEqual(new, [("ingest", "core.model_suite")])
        self.assertEqual(stale, [])

    def test_agrifusion_does_not_import_backend_or_benchmark(self) -> None:
        """Hard rule, independent of the allow-list: agrifusion never depends on Backend/ or agrifusion_research."""
        offending = [
            f"{src} -> {dst}" for (src, dst) in build_edges()
            if src in AGRIFUSION_NODES and (dst in RESEARCH_NODE_PREFIXES or dst.startswith(RESEARCH_NODE_PREFIXES) or dst == "Backend")
        ]
        self.assertEqual(offending, [])

    def test_ingest_and_canonical_stay_independent(self) -> None:
        """Layer0 (ingest) and Layer1 (canonical) meet only in the CLI, never import each other."""
        edges = set(build_edges())
        self.assertNotIn(("ingest", "canonical"), edges)
        self.assertNotIn(("canonical", "ingest"), edges)

    def test_leaf_packages_have_no_upward_imports(self) -> None:
        """settings and io are leaves: they import no other agrifusion subpackage except settings -> none."""
        for src, dst in build_edges():
            if src in {"settings", "io"}:
                self.assertNotIn(dst, AGRIFUSION_NODES, f"{src} -> {dst}")

    def test_no_sys_path_hacks_inside_agrifusion(self) -> None:
        offending = [
            path.relative_to(REPO_ROOT).as_posix()
            for path in (REPO_ROOT / "src" / "agrifusion").rglob("*.py")
            if "sys.path" in path.read_text(encoding="utf-8")
        ]
        self.assertEqual(offending, [])


if __name__ == "__main__":
    unittest.main()
