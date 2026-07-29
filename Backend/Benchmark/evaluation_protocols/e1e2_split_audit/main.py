from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from Backend.Benchmark.evaluation_protocols.e1e2_split_audit import build_e1e2_split_audit


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit whether a combined E1+E2 chronological 70/15/15 split keeps full class support.",
    )
    parser.add_argument(
        "--protocol-run-dir",
        type=Path,
        required=True,
        help="Path to an evaluation_protocols artifact run.",
    )
    parser.add_argument(
        "--weak-labels-run-dir",
        type=Path,
        required=True,
        help="Path to a weak_labels artifact run.",
    )
    parser.add_argument("--train-ratio", type=float, default=0.70)
    parser.add_argument("--validation-ratio", type=float, default=0.15)
    parser.add_argument("--test-ratio", type=float, default=0.15)
    parser.add_argument(
        "--split-strategy",
        type=str,
        default="chronological_v1",
        choices=("chronological_v1",),
        help="Shared benchmark split strategy used for the audit.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    result = build_e1e2_split_audit(
        protocol_run_dir=args.protocol_run_dir.resolve(),
        weak_labels_run_dir=args.weak_labels_run_dir.resolve(),
        train_ratio=args.train_ratio,
        validation_ratio=args.validation_ratio,
        test_ratio=args.test_ratio,
        split_strategy=args.split_strategy,
    )
    print("E1+E2 split audit complete")
    print(f"Run id: {result['run_id']}")
    print(f"Output dir: {result['output_dir']}")
    print(result["summary"].to_string(index=False))


if __name__ == "__main__":
    main()
