from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from Backend.Benchmark.dataset_views.configs import DEFAULT_PUBLIC_VIEW_IDS, SUPPORTED_MODES
from Backend.Benchmark.dataset_views.contracts import LabelConfig, MaterializationConfig
from Backend.Benchmark.dataset_views.pipelines import materialize_dataset_views
from Backend.Config.paths import BACKEND_PATHS


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Materialize row-wise benchmark dataset views directly from frozen Layer1 canonical history."
    )
    parser.add_argument(
        "--mode",
        choices=SUPPORTED_MODES,
        default="feature-only",
        help="Materialization mode. benchmark-ready requires an explicit label artifact keyed by record.id.",
    )
    parser.add_argument(
        "--views",
        nargs="+",
        default=list(DEFAULT_PUBLIC_VIEW_IDS),
        help="Dataset semantic view ids or numeric aliases to materialize.",
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
        help="Optional Layer1 manifest JSON.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=BACKEND_PATHS.benchmark_dir / "dataset_views" / "artifacts",
        help="Output root under which a new run directory will be created.",
    )
    parser.add_argument(
        "--label-artifact",
        type=Path,
        default=None,
        help="Explicit label artifact keyed by record.id. Required for benchmark-ready mode.",
    )
    parser.add_argument(
        "--label-columns",
        nargs="+",
        default=(),
        help="Required label columns that must exist in the label artifact.",
    )
    parser.add_argument(
        "--legacy-event-csv",
        type=Path,
        default=BACKEND_PATHS.benchmark_dir / "benchmark_dataset" / "dataset" / "benchmark_input_labeled.csv",
        help="Legacy weak-label CSV used to bridge V3 operational-lineage events onto canonical history.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    label_config = None
    if args.label_artifact is not None:
        label_config = LabelConfig(
            artifact_path=args.label_artifact.resolve(),
            required_columns=tuple(args.label_columns),
        )

    result = materialize_dataset_views(
        MaterializationConfig(
            canonical_history_path=args.canonical_history.resolve(),
            feature_catalog_path=args.feature_catalog.resolve(),
            manifest_path=args.layer1_manifest.resolve() if args.layer1_manifest is not None else None,
            output_root=args.output_root.resolve(),
            mode=args.mode,
            selected_views=tuple(args.views),
            label_config=label_config,
            legacy_event_csv_path=args.legacy_event_csv.resolve() if args.legacy_event_csv is not None else None,
        )
    )

    print("Dataset view materialization complete")
    print(f"Run id: {result.run_id}")
    print(f"Output dir: {result.output_dir}")
    print(f"Mode: {args.mode}")
    print(f"Label status: {result.label_status}")
    print(f"Views: {', '.join(result.selected_views)}")
    print(f"Rows: {result.row_count}")
    if result.materialized_nonpublic_drafts:
        print(f"Internal drafts: {', '.join(result.materialized_nonpublic_drafts)}")


if __name__ == "__main__":
    main()
