from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[4]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from Backend.Benchmark.common.paths import WEAK_LABELS_ROOT
from Backend.Benchmark.weak_labels.analysis.unres_origin_split import (
    UnresOriginSplitConfig,
    build_unres_origin_split,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build an audit-only temporal UNRES origin split.")
    parser.add_argument("--release-dir", type=Path, required=True)
    parser.add_argument("--protocol-run-dir", type=Path, default=None)
    parser.add_argument("--horizon-id", choices=("3h", "8h"), default="3h")
    parser.add_argument("--output-root", type=Path, default=WEAK_LABELS_ROOT / "artifacts" / "phase_c")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = build_unres_origin_split(
        UnresOriginSplitConfig(
            release_dir=args.release_dir,
            output_root=args.output_root,
            protocol_run_dir=args.protocol_run_dir,
            horizon_id=args.horizon_id,
        )
    )
    print("temporal UNRES origin split complete")
    print(f"run_id: {result.run_id}")
    print(f"output_dir: {result.output_dir}")
    print(f"native_rows: {result.native_row_count}")
    print(f"native_UNRES_K: {result.native_unres_k_count}")
    print(f"native_UNRES_A: {result.native_unres_a_count}")


if __name__ == "__main__":
    main()
