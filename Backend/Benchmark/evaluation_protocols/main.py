from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from Backend.Benchmark.common.paths import EVALUATION_PROTOCOLS_ROOT
from Backend.Benchmark.evaluation_protocols import EvaluationProtocolConfig, build_evaluation_protocols
from Backend.Config.paths import BACKEND_PATHS


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build evaluation-protocol artifacts by joining canonical telemetry, dataset views, and a native label release."
    )
    parser.add_argument("--canonical-history", type=Path, default=BACKEND_PATHS.layer1_dir / "canonical" / "telemetry_history.csv")
    parser.add_argument("--protocol-registry-run-dir", type=Path, required=True)
    parser.add_argument(
        "--protocol-stage-id",
        type=str,
        default="RQ2B_E3_REEVALUATION_BATCH",
        help="Governed stage authorizing the native-label evaluation artifacts.",
    )
    parser.add_argument("--feature-catalog", type=Path, default=BACKEND_PATHS.layer1_dir / "canonical" / "feature_catalog.csv")
    parser.add_argument("--layer1-manifest", type=Path, default=BACKEND_PATHS.layer1_dir / "manifest.json")
    parser.add_argument("--segment-manifest", type=Path, default=None)
    parser.add_argument("--dataset-views-run-dir", type=Path, required=True)
    parser.add_argument("--native-label-release-dir", type=Path, required=True)
    parser.add_argument(
        "--execution-profile",
        type=Path,
        default=None,
        help="YAML environment scope; omit to use the compatibility P1/P2 profile.",
    )
    parser.add_argument("--output-root", type=Path, default=EVALUATION_PROTOCOLS_ROOT / "artifacts")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dataset_views_run_dir = args.dataset_views_run_dir.resolve()
    result = build_evaluation_protocols(
        EvaluationProtocolConfig(
            protocol_registry_run_dir=args.protocol_registry_run_dir.resolve(),
            protocol_stage_id=args.protocol_stage_id,
            canonical_history_path=args.canonical_history.resolve(),
            feature_catalog_path=args.feature_catalog.resolve(),
            manifest_path=args.layer1_manifest.resolve(),
            segment_manifest_path=args.segment_manifest.resolve() if args.segment_manifest is not None else None,
            dataset_views_run_dir=dataset_views_run_dir,
            native_label_release_dir=args.native_label_release_dir.resolve(),
            output_root=args.output_root.resolve(),
            execution_profile_path=args.execution_profile.resolve() if args.execution_profile is not None else None,
        )
    )
    print("evaluation_protocols build complete")
    print(f"Run id: {result.run_id}")
    print(f"Output dir: {result.output_dir}")
    print(f"P1 rows: {result.source_row_count}")
    print(f"P2 rows: {result.target_row_count}")


if __name__ == "__main__":
    main()
