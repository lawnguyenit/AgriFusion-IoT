from __future__ import annotations

from pathlib import Path

from Backend.Config.path_manager import get_benchmark_path


LAYER3_COMBO_ROOT = Path(__file__).resolve().parents[1]
DATASET_ROOT = get_benchmark_path() / "fuzzy_logic_basic" / "dataset"
DEFAULT_INPUT_CSV = DATASET_ROOT / "flb_input_aligned.csv"
DEFAULT_OUTPUT_DIR = DATASET_ROOT

