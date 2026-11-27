"""Well-known locations for the research lane.

Code lives in ``research/agrifusion_research``; everything it generates goes under
``<project root>/output/research/<lane>/`` (gitignored), never next to the code.
Artifacts written before GD5 live under ``Backend/Benchmark/<lane>/artifacts``; move them to
``output/research/<lane>/artifacts`` to keep using them with the default paths.
"""
from __future__ import annotations

from pathlib import Path

from agrifusion.settings.paths import BACKEND_PATHS

REPO_ROOT: Path = BACKEND_PATHS.project_root
PACKAGE_ROOT: Path = Path(__file__).resolve().parents[2]
RESEARCH_OUTPUT_ROOT: Path = BACKEND_PATHS.output_dir / "research"
LAYER1_ROOT: Path = BACKEND_PATHS.layer1_dir

PROTOCOL_REGISTRY_ROOT: Path = RESEARCH_OUTPUT_ROOT / "protocol_registry"
DATASET_VIEWS_ROOT: Path = RESEARCH_OUTPUT_ROOT / "dataset_views"
WEAK_LABELS_ROOT: Path = RESEARCH_OUTPUT_ROOT / "weak_labels"
EVALUATION_PROTOCOLS_ROOT: Path = RESEARCH_OUTPUT_ROOT / "evaluation_protocols"
VALIDITY_LIFECYCLE_ROOT: Path = RESEARCH_OUTPUT_ROOT / "validity_lifecycle"
MODEL_SUITE_ROOT: Path = RESEARCH_OUTPUT_ROOT / "model_suite"


def lane_output_root(lane: str) -> Path:
    """``output/research/<lane>``: the default home of a lane's run directories."""
    return RESEARCH_OUTPUT_ROOT / lane
