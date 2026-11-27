from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from .grid import summarize_candidate_support_by_partition


def main() -> int:
    parser = argparse.ArgumentParser(description="Write descriptive per-split candidate support; no gate is applied.")
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--splits", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = summarize_candidate_support_by_partition(
        labels=pd.read_parquet(args.labels),
        registry=pd.read_csv(args.registry),
        splits=pd.read_parquet(args.splits),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.output, index=False)
    print(json.dumps({"output": str(args.output.resolve()), "candidate_partition_rows": len(result), "gate_applied": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
