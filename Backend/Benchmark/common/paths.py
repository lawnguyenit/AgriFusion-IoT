from __future__ import annotations

from pathlib import Path

from Backend.Config.paths import BACKEND_PATHS


BACKEND_ROOT: Path = BACKEND_PATHS.backend_dir
BENCHMARK_ROOT: Path = BACKEND_PATHS.benchmark_dir
DATASET_VIEWS_ROOT: Path = BENCHMARK_ROOT / "dataset_views"
WEAK_LABELS_ROOT: Path = BENCHMARK_ROOT / "weak_labels"
EVALUATION_PROTOCOLS_ROOT: Path = BENCHMARK_ROOT / "evaluation_protocols"
VALIDITY_LIFECYCLE_ROOT: Path = BENCHMARK_ROOT / "validity_lifecycle"
MODEL_SUITE_ROOT: Path = BENCHMARK_ROOT / "model_suite"
