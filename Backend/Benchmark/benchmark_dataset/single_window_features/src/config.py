from __future__ import annotations

from pathlib import Path

from Backend.Config.paths import BACKEND_PATHS


LAYER2_ROOT = Path(__file__).resolve().parents[1]
DATASET_ROOT = BACKEND_PATHS.benchmark_dir / "benchmark_dataset" / "dataset"
DEFAULT_INPUT_CSV = DATASET_ROOT / "benchmark_input_labeled.csv"
DEFAULT_OUTPUT_DIR = DATASET_ROOT
SATURATION_THRESHOLD = 95.0
