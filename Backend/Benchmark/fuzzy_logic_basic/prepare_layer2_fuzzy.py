from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from Backend.Benchmark.fuzzy_logic_basic.core.runner import (  # noqa: E402
    default_layer1_root,
    default_output_root,
    materialize_layer2_fuzzy,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build Layer2/fuzzy CSV from Layer1 histories using explicit anchor_time rows."
    )
    parser.add_argument("--layer1-root", type=Path, default=default_layer1_root())
    parser.add_argument("--output-root", type=Path, default=default_output_root())
    parser.add_argument("--limit", type=int, default=None, help="Optional row limit for a dry run.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = materialize_layer2_fuzzy(
        layer1_root=args.layer1_root,
        output_root=args.output_root,
        limit=args.limit,
    )
    print("Layer2 fuzzy materialization complete")
    print(f"Input root: {result.input_root}")
    print(f"Output root: {result.output_root}")
    print(f"CSV: {result.csv_path}")
    print(f"Manifest: {result.manifest_path}")
    print(f"Anchor count: {result.anchor_count}")
    print(f"Row count: {result.row_count}")


if __name__ == "__main__":
    main()
