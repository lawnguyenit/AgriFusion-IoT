from __future__ import annotations

import argparse
import json
from pathlib import Path

from .contracts import PretrainAuditConfig
from .pipeline import run_pretrain_audit


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Select and audit feature groups before training.")
    parser.add_argument("--feature-matrix", type=Path, required=True)
    parser.add_argument("--feature-registry", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--splits", type=Path, required=True)
    parser.add_argument("--groups", nargs="+", required=True, help="Feature group IDs present in the registry.")
    parser.add_argument("--targets", nargs="+", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--max-missing-fraction", type=float)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = run_pretrain_audit(
        PretrainAuditConfig(
            feature_matrix_path=args.feature_matrix,
            feature_registry_path=args.feature_registry,
            labels_path=args.labels,
            splits_path=args.splits,
            selected_groups=tuple(args.groups),
            target_columns=tuple(args.targets),
            output_root=args.output_root,
            max_missing_fraction=args.max_missing_fraction,
        )
    )
    print(
        json.dumps(
            {
                "run_id": result.run_id,
                "output_dir": str(result.output_dir),
                "rows": result.row_count,
                "features": result.feature_count,
                "targets": result.target_count,
                "audit_status": result.status,
            },
            ensure_ascii=True,
        )
    )
    return 0 if result.status != "blocked" else 2


if __name__ == "__main__":
    raise SystemExit(main())
