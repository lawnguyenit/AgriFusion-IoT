from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from .pipeline import run_claim_inventory


def main() -> int:
    parser = argparse.ArgumentParser(description="Inventory dataset evidence before selecting semantic label claims.")
    parser.add_argument("--canonical", type=Path, required=True)
    parser.add_argument("--intake-manifest", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--min-observations", type=int, default=100)
    parser.add_argument("--dataset-id", help="Override when the source manifest does not contain dataset_id.")
    parser.add_argument("--feature-catalog", type=Path, help="Optional Core feature_catalog.csv for canonical field roles.")
    parser.add_argument("--timestamp-column", help="Timestamp column for sources without a column named timestamp.")
    parser.add_argument("--entity-column", help="Optional entity/group key for per-entity cadence summaries.")
    args = parser.parse_args()
    result = run_claim_inventory(
        canonical_path=args.canonical,
        manifest_path=args.intake_manifest,
        output_root=args.output_root,
        min_observations=args.min_observations,
        dataset_id=args.dataset_id,
        feature_catalog_path=args.feature_catalog,
        timestamp_column=args.timestamp_column,
        entity_column=args.entity_column,
    )
    print(json.dumps({
        "dataset_id": result.dataset_id,
        "output_dir": str(result.output_dir),
        "rows": result.row_count,
        "relative_state_candidates": result.candidate_state_count,
        "claim_gate": "REVIEW_REQUIRED",
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
