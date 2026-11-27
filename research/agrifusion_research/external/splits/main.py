from __future__ import annotations

import argparse
from pathlib import Path

from .contracts import ExternalSplitConfig
from .pipeline import build_external_timestamp_split


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a chronological global timestamp-block external split.")
    parser.add_argument("--canonical", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--timestamp-column", default="timestamp")
    parser.add_argument("--group-columns", default="")
    parser.add_argument("--shared-timestamp-columns", default="")
    parser.add_argument("--train-ratio", type=float, default=0.70)
    parser.add_argument("--validation-ratio", type=float, default=0.15)
    parser.add_argument("--test-ratio", type=float, default=0.15)
    args = parser.parse_args()
    config = ExternalSplitConfig(
        canonical_path=args.canonical,
        output_root=args.output_root,
        timestamp_column=args.timestamp_column,
        group_columns=tuple(value.strip() for value in args.group_columns.split(",") if value.strip()),
        shared_timestamp_columns=tuple(value.strip() for value in args.shared_timestamp_columns.split(",") if value.strip()),
        train_ratio=args.train_ratio,
        validation_ratio=args.validation_ratio,
        test_ratio=args.test_ratio,
    )
    result = build_external_timestamp_split(config)
    print(result.splits_path)
    print(f"rows={result.row_count} timestamps={result.timestamp_block_count}")


if __name__ == "__main__":
    main()
