"""external/datasets.py is the only place that knows dataset ids (GD5 s5e)."""
from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

from agrifusion_research.external.datasets import REGISTRY, dataset_ids, get_dataset_profile
from agrifusion_research.external.features.profiles import resolve_profile as feature_profile
from agrifusion_research.external.intake.adapters import ADAPTERS
from agrifusion_research.external.intake.persistence import make_run_id
from agrifusion_research.external.intake.sources import DATASET_METADATA, SOURCE_FILES
from agrifusion_research.external.labels.profiles import PROFILES, resolve_profile as label_profile

EXTERNAL = Path(__file__).resolve().parents[2] / "research" / "agrifusion_research" / "external"


class ExternalRegistryTests(unittest.TestCase):
    def test_every_lane_reads_the_same_profile(self) -> None:
        self.assertEqual(dataset_ids(), ("stuard_tomato_irrigation_2023", "uci_air_quality_360"))
        for dataset_id, profile in REGISTRY.items():
            self.assertIn(profile.intake_adapter, ADAPTERS)
            self.assertIs(feature_profile(dataset_id, {}), profile.features)
            self.assertIs(label_profile(dataset_id), profile.labels)
            self.assertIs(PROFILES[dataset_id], profile.labels)
            self.assertEqual(SOURCE_FILES[dataset_id], profile.source_files)
            self.assertEqual(DATASET_METADATA[dataset_id], dict(profile.metadata))

    def test_unknown_dataset_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            get_dataset_profile("nope")

    def test_run_id_prefix_is_kept_for_lineage(self) -> None:
        self.assertRegex(make_run_id("uci_air_quality_360"), r"^external_intake_uci_air_quality_360_\d{8}T\d{12}Z$")

    def test_no_dataset_id_branches_in_lane_code(self) -> None:
        ids = set(dataset_ids())
        offending = []
        for path in EXTERNAL.rglob("*.py"):
            if path.name == "datasets.py" or "adapters" in path.parts:
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in ids:
                    offending.append(f"{path.relative_to(EXTERNAL)}:{node.lineno}")
        self.assertEqual(offending, [])


if __name__ == "__main__":
    unittest.main()
