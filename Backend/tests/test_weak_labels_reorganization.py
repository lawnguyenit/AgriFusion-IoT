from __future__ import annotations

import importlib
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WEAK_LABELS = ROOT / "Benchmark" / "weak_labels"


class WeakLabelsReorganizationTests(unittest.TestCase):
    def test_target_namespaces_exist(self) -> None:
        expected = (
            "contracts",
            "lifecycle",
            "semantic",
            "provenance",
            "infrastructure",
            "compatibility",
        )
        for name in expected:
            self.assertTrue((WEAK_LABELS / name / "__init__.py").exists(), name)

    def test_obsolete_root_implementation_dirs_have_been_removed(self) -> None:
        obsolete = (
            "native_engine",
            "readiness",
            "semantic_contract",
            "io",
            "shared",
            "runtime",
            "point",
            "v2",
            "partitions",
            "reporting",
        )
        for name in obsolete:
            path = WEAK_LABELS / name
            source_files = list(path.glob("*.py")) if path.exists() else []
            self.assertEqual(source_files, [], name)

    def test_lifecycle_public_apis_are_importable(self) -> None:
        phase_a = importlib.import_module("Backend.Benchmark.weak_labels.lifecycle.phase_a_readiness")
        phase_b = importlib.import_module("Backend.Benchmark.weak_labels.lifecycle.phase_b_contract")
        phase_c = importlib.import_module("Backend.Benchmark.weak_labels.lifecycle.phase_c_native")
        self.assertTrue(callable(phase_a.build_phase_a_readiness))
        self.assertTrue(callable(phase_b.build_phase_b_decision_pack))
        self.assertTrue(callable(phase_c.build_native_label_artifacts))

    def test_root_api_exposes_native_lifecycle_only(self) -> None:
        module = importlib.import_module("Backend.Benchmark.weak_labels")
        self.assertTrue(callable(module.build_native_label_artifacts))
        self.assertFalse(hasattr(module, "build_weak_labels"))

    def test_provenance_ids_are_namespaced(self) -> None:
        provenance = importlib.import_module("Backend.Benchmark.weak_labels.provenance")
        first = provenance.build_deterministic_id(
            {"object_type": "RULE_FIRING", "schema_version": "v1", "sample_id": "r1"}
        )
        second = provenance.build_deterministic_id(
            {"object_type": "ASSIGNMENT", "schema_version": "v1", "sample_id": "r1"}
        )
        self.assertNotEqual(first, second)

    def test_governance_does_not_import_weak_labels(self) -> None:
        registry_root = ROOT / "Benchmark" / "protocol_registry"
        for path in registry_root.rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("import Backend.Benchmark.weak_labels", source, str(path))
            self.assertNotIn("from Backend.Benchmark.weak_labels", source, str(path))

    def test_evaluation_callers_use_new_facades(self) -> None:
        caller_paths = (
            ROOT / "Benchmark" / "evaluation_protocols" / "pipeline" / "build.py",
            ROOT / "Benchmark" / "evaluation_protocols" / "domains" / "thresholds.py",
            ROOT / "Benchmark" / "evaluation_protocols" / "diagnostics" / "sensitivity.py",
        )
        for path in caller_paths:
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("weak_labels.point", source, str(path))
            self.assertNotIn("weak_labels.v2", source, str(path))
            self.assertNotIn("compatibility.legacy_", source, str(path))


if __name__ == "__main__":
    unittest.main()
