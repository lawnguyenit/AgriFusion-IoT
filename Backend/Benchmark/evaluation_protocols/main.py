from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from Backend.Benchmark.common.paths import DATASET_VIEWS_ROOT, EVALUATION_PROTOCOLS_ROOT, WEAK_LABELS_ROOT
from Backend.Benchmark.evaluation_protocols import EvaluationProtocolConfig, build_evaluation_protocols
from Backend.Config.paths import BACKEND_PATHS


def _default_latest_weak_labels_run() -> Path:
    artifacts_root = WEAK_LABELS_ROOT / "artifacts"
    candidates = [path for path in artifacts_root.iterdir() if path.is_dir()] if artifacts_root.exists() else []
    if not candidates:
        raise FileNotFoundError("No weak_labels artifact runs were found under Backend/Benchmark/weak_labels/artifacts.")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _default_latest_dataset_views_run() -> Path:
    artifacts_root = DATASET_VIEWS_ROOT / "artifacts"
    candidates = [path for path in artifacts_root.iterdir() if path.is_dir()] if artifacts_root.exists() else []
    if not candidates:
        raise FileNotFoundError("No dataset_views artifact runs were found under Backend/Benchmark/dataset_views/artifacts.")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build simplified P1/P2 evaluation-protocol artifacts from canonical telemetry and a weak-label authority run."
    )
    parser.add_argument("--canonical-history", type=Path, default=BACKEND_PATHS.layer1_dir / "canonical" / "telemetry_history.csv")
    parser.add_argument("--feature-catalog", type=Path, default=BACKEND_PATHS.layer1_dir / "canonical" / "feature_catalog.csv")
    parser.add_argument("--layer1-manifest", type=Path, default=BACKEND_PATHS.layer1_dir / "manifest.json")
    parser.add_argument("--segment-manifest", type=Path, default=None)
    parser.add_argument("--dataset-views-run-dir", type=Path, default=None)
    parser.add_argument("--weak-labels-run-dir", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, default=EVALUATION_PROTOCOLS_ROOT / "artifacts")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dataset_views_run_dir = (
        args.dataset_views_run_dir.resolve()
        if args.dataset_views_run_dir is not None
        else _default_latest_dataset_views_run().resolve()
    )
    weak_labels_run_dir = args.weak_labels_run_dir.resolve() if args.weak_labels_run_dir is not None else _default_latest_weak_labels_run().resolve()
    result = build_evaluation_protocols(
        EvaluationProtocolConfig(
            canonical_history_path=args.canonical_history.resolve(),
            feature_catalog_path=args.feature_catalog.resolve(),
            manifest_path=args.layer1_manifest.resolve(),
            segment_manifest_path=args.segment_manifest.resolve() if args.segment_manifest is not None else None,
            dataset_views_run_dir=dataset_views_run_dir,
            weak_labels_run_dir=weak_labels_run_dir,
            output_root=args.output_root.resolve(),
        )
    )
    print("evaluation_protocols build complete")
    print(f"Run id: {result.run_id}")
    print(f"Output dir: {result.output_dir}")
    print(f"P1 rows: {result.source_row_count}")
    print(f"P2 rows: {result.target_row_count}")


if __name__ == "__main__":
    main()
