from __future__ import annotations

import argparse
import json
from pathlib import Path

from .contracts import ExternalFeatureConfig
from .pipeline import run_external_feature_processing


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build value and causal-window features for an external intake run.")
    parser.add_argument("--canonical", type=Path, required=True)
    parser.add_argument("--intake-manifest", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--window-hours", nargs="+", type=int, default=[3, 8])
    parser.add_argument("--min-window-observations", type=int, default=2)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = run_external_feature_processing(
        ExternalFeatureConfig(
            canonical_path=args.canonical,
            intake_manifest_path=args.intake_manifest,
            output_root=args.output_root,
            window_hours=tuple(args.window_hours),
            min_window_observations=args.min_window_observations,
        )
    )
    print(
        json.dumps(
            {
                "dataset_id": result.dataset_id,
                "run_id": result.run_id,
                "output_dir": str(result.output_dir),
                "feature_matrix_path": str(result.feature_matrix_path),
                "registry_path": str(result.registry_path),
                "rows": result.row_count,
                "features": result.feature_count,
            },
            ensure_ascii=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
