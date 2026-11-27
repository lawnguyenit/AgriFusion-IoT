from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from agrifusion_research.external.datasets import dataset_ids  # noqa: E402
from agrifusion_research.external.intake.pipeline import ExternalIntakeConfig, run_external_intake  # noqa: E402


DEFAULT_PACK_ROOT = ROOT_DIR / "Backend" / "Output_data" / "wade_external_validation_pack"
DATASET_IDS = dataset_ids()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Preserve and canonicalize one external benchmark dataset.")
    parser.add_argument("--dataset", choices=DATASET_IDS, required=True)
    parser.add_argument("--input-dir", type=Path, help="Directory containing the unmodified source file(s).")
    parser.add_argument("--download", action="store_true", help="Download source files into a new immutable raw release.")
    parser.add_argument("--release-id", help="Optional new raw release folder name; never overwrite an existing release.")
    parser.add_argument("--raw-root", type=Path, default=DEFAULT_PACK_ROOT / "raw")
    parser.add_argument("--processed-root", type=Path, default=DEFAULT_PACK_ROOT / "processed")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run_external_intake(
        ExternalIntakeConfig(
            dataset_id=args.dataset,
            input_dir=args.input_dir,
            raw_root=args.raw_root,
            processed_root=args.processed_root,
            download=args.download,
            release_id=args.release_id,
        )
    )
    print(f"External intake complete: {result.run_id}")
    print(f"Raw: {result.raw_dir}")
    print(f"Processed: {result.output_dir}")
    print(f"Rows: {result.row_count}; excluded: {result.excluded_row_count}")


if __name__ == "__main__":
    main()
