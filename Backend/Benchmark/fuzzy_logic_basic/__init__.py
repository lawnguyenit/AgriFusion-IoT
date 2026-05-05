"""Basic fuzzy logic benchmark for AgriFusion-IoT."""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from .core import default_layer1_root, default_output_root, materialize_layer2_fuzzy
