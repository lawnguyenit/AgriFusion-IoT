"""CLI for post-hoc model-suite analyses."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[4]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from Backend.Benchmark.model_suite.analysis.unres_origin_prediction_join import (
    DEFAULT_FEATURE_VIEW_IDS,
    UnresOriginPredictionJoinConfig,
    build_unres_origin_prediction_join,
)
from Backend.Benchmark.model_suite.analysis.event_online_comparison import (
    build_event_online_comparison,
)
from Backend.Benchmark.model_suite.analysis.online_run_depth_stratification import (
    OnlineRunDepthStratificationConfig,
    build_online_run_depth_stratification,
)
from Backend.Benchmark.model_suite.analysis.provenance_strata_analysis import (
    ProvenanceStrataAnalysisConfig,
    build_provenance_strata_analysis,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run post-hoc model-suite analyses.")
    parser.add_argument("--model-run-dir", type=Path, required=True, help="Existing model-suite run directory.")
    artifact_group = parser.add_mutually_exclusive_group(required=True)
    artifact_group.add_argument("--unres-origin-artifact-dir", type=Path, help="Derived UNRES-origin artifact directory.")
    artifact_group.add_argument("--target-views-artifact-dir", type=Path, help="Derived paired event/online target-view artifact directory.")
    artifact_group.add_argument("--run-depth-target-views-artifact-dir", type=Path, help="Target-view artifact for the post-hoc Y_online run-depth analysis.")
    artifact_group.add_argument("--provenance-strata-target-views-artifact-dir", type=Path, help="Target-view artifact for the five-strata provenance analysis.")
    parser.add_argument("--output-root", type=Path, default=None, help="Sibling artifact root; defaults to model run parent.")
    parser.add_argument("--feature-view-ids", nargs="+", default=list(DEFAULT_FEATURE_VIEW_IDS))
    parser.add_argument("--partitions", nargs="+", default=["test"])
    parser.add_argument("--profile", default="temporal_event_online_3h", help="Model profile for paired target analysis.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.provenance_strata_target_views_artifact_dir is not None:
        result = build_provenance_strata_analysis(
            ProvenanceStrataAnalysisConfig(
                model_suite_run_dir=args.model_run_dir,
                target_views_artifact_dir=args.provenance_strata_target_views_artifact_dir,
                output_root=args.output_root,
                profile_name=args.profile,
                feature_view_ids=tuple(args.feature_view_ids),
                partitions=tuple(args.partitions),
            )
        )
        print(json.dumps({
            "run_id": result.run_id,
            "output_dir": str(result.output_dir),
            "provenance_row_count": result.provenance_row_count,
            "online_prediction_row_count": result.online_prediction_row_count,
            "event_prediction_row_count": result.event_prediction_row_count,
            "paired_prediction_row_count": result.paired_prediction_row_count,
        }, ensure_ascii=False, indent=2))
        return 0
    if args.run_depth_target_views_artifact_dir is not None:
        result = build_online_run_depth_stratification(
            OnlineRunDepthStratificationConfig(
                model_suite_run_dir=args.model_run_dir,
                target_views_artifact_dir=args.run_depth_target_views_artifact_dir,
                output_root=args.output_root,
                profile_name=args.profile,
                feature_view_ids=tuple(args.feature_view_ids),
                partitions=tuple(args.partitions),
            )
        )
        print(json.dumps({
            "run_id": result.run_id,
            "output_dir": str(result.output_dir),
            "q_positive_row_count": result.q_positive_row_count,
            "prediction_row_count": result.prediction_row_count,
            "summary_row_count": result.summary_row_count,
        }, ensure_ascii=False, indent=2))
        return 0
    if args.target_views_artifact_dir is not None:
        result = build_event_online_comparison(
            model_suite_run_dir=args.model_run_dir,
            target_views_artifact_dir=args.target_views_artifact_dir,
            output_root=(args.output_root or args.model_run_dir.parent),
            profile_name=args.profile,
        )
        print(json.dumps({
            "run_id": result.run_id,
            "output_dir": str(result.output_dir),
            "g_total_count": result.g_total_count,
            "g_evaluable_count": result.g_evaluable_count,
            "g_unique_evaluable_count": result.g_unique_evaluable_count,
            "metric_row_count": result.metric_row_count,
        }, ensure_ascii=False, indent=2))
        return 0
    result = build_unres_origin_prediction_join(
        UnresOriginPredictionJoinConfig(
            model_run_dir=args.model_run_dir,
            unres_origin_artifact_dir=args.unres_origin_artifact_dir,
            output_root=args.output_root,
            feature_view_ids=tuple(args.feature_view_ids),
            partitions=tuple(args.partitions),
        )
    )
    print(json.dumps({
        "run_id": result.run_id,
        "output_dir": str(result.output_dir),
        "joined_row_count": result.joined_row_count,
        "confusion_rows": result.confusion_rows,
        "coverage_rows": result.coverage_rows,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
