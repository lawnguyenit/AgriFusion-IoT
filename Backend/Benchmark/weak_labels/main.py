from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from Backend.Benchmark.common.paths import WEAK_LABELS_ROOT
from Backend.Benchmark.weak_labels.runtime import WeakLabelsConfig, build_weak_labels
from Backend.Config.paths import BACKEND_PATHS


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build versioned weak-label artifacts from frozen canonical telemetry."
    )
    parser.add_argument(
        "--canonical-history",
        type=Path,
        default=BACKEND_PATHS.layer1_dir / "canonical" / "telemetry_history.csv",
        help="Frozen Layer1 canonical history CSV.",
    )
    parser.add_argument(
        "--feature-catalog",
        type=Path,
        default=BACKEND_PATHS.layer1_dir / "canonical" / "feature_catalog.csv",
        help="Layer1 feature catalog CSV.",
    )
    parser.add_argument(
        "--layer1-manifest",
        type=Path,
        default=BACKEND_PATHS.layer1_dir / "manifest.json",
        help="Layer1 manifest JSON used to resolve the segment manifest when not passed explicitly.",
    )
    parser.add_argument(
        "--segment-manifest",
        type=Path,
        default=None,
        help="Optional explicit segment manifest JSON.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=WEAK_LABELS_ROOT / "artifacts",
        help="Output root for weak-label runs.",
    )
    parser.add_argument(
        "--base-split-strategy",
        choices=("chronological_v1",),
        default="chronological_v1",
        help="Base split strategy before view-specific effective exclusions.",
    )
    parser.add_argument(
        "--run-profile",
        choices=("chronological_temporal", "segment_holdout_last"),
        default="chronological_temporal",
        help="Run profile controlling base partition semantics.",
    )
    parser.add_argument(
        "--threshold-mode",
        choices=("TRAIN_FITTED_GLOBAL", "TRAIN_FITTED_SEGMENT"),
        default="TRAIN_FITTED_GLOBAL",
        help="Threshold fitting mode for weak environmental rules.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = build_weak_labels(
        WeakLabelsConfig(
            canonical_history_path=args.canonical_history.resolve(),
            feature_catalog_path=args.feature_catalog.resolve(),
            manifest_path=args.layer1_manifest.resolve() if args.layer1_manifest is not None else None,
            segment_manifest_path=args.segment_manifest.resolve() if args.segment_manifest is not None else None,
            output_root=args.output_root.resolve(),
            base_split_strategy=args.base_split_strategy,
            run_profile=args.run_profile,
            threshold_mode=args.threshold_mode,
        )
    )
    print("weak_labels build complete")
    print(f"Run id: {result.run_id}")
    print(f"Output dir: {result.output_dir}")
    print(f"Rows: {result.row_count}")


if __name__ == "__main__":
    main()
