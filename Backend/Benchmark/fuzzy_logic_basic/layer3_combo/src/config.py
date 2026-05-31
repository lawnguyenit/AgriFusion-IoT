from __future__ import annotations

from pathlib import Path

from Backend.Config.paths import BACKEND_PATHS


LAYER3_COMBO_ROOT = Path(__file__).resolve().parents[1]
DATASET_ROOT = BACKEND_PATHS.benchmark_dir / "fuzzy_logic_basic" / "dataset"
DEFAULT_INPUT_CSV = DATASET_ROOT / "flb_input_aligned.csv"
DEFAULT_OUTPUT_DIR = DATASET_ROOT
