from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[5]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from Backend.Benchmark.model_suite.analysis.k_window_variants.history import FeatureBundle, build_causal_history_bundle
from Backend.Benchmark.model_suite.analysis.k_window_variants.representations import build_representation_bundles
from Backend.Benchmark.model_suite.analysis.k_window_variants.robustness_audit import (
    build_threshold_history_oracle,
    build_unres_audit,
    summarize_threshold_oracle,
)
from Backend.Benchmark.model_suite.analysis.k_window_variants.robustness_features import build_history_audit_representations
from Backend.Benchmark.model_suite.analysis.k_window_variants.robustness_reporting import write_robustness_outputs
from Backend.Benchmark.model_suite.analysis.k_window_variants.robustness_runner import (
    build_audit_variants,
    build_temporal_fold_frames,
    run_single_fold_audit,
    run_temporal_cv,
    summarize_cv_metrics,
)
from Backend.Benchmark.model_suite.analysis.k_window_variants.runner import load_feature_matrix
from Backend.Benchmark.model_suite.analysis.k_window_variants.semantic_targets import load_online_event_target_frame
from Backend.Benchmark.shared.artifacts import create_run_directory


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run history robustness, provenance, temporal-fold, and oracle audits.")
    parser.add_argument("--snapshot-run-dir", type=Path, default=ROOT_DIR / "Backend/Benchmark/dataset_views/artifacts/dataset_views_20260729_164926_756176")
    parser.add_argument("--window-run-dir", type=Path, default=ROOT_DIR / "Backend/Benchmark/dataset_views/artifacts/dataset_views_20260729_164926_175188")
    parser.add_argument("--native-release-dir", type=Path, default=ROOT_DIR / "Backend/Benchmark/weak_labels/artifacts/phase_c/native_engine_20260805_045419_359073")
    parser.add_argument("--protocol-run-dir", type=Path, default=ROOT_DIR / "Backend/Benchmark/evaluation_protocols/artifacts/evaluation_protocols_20260902_203645")
    parser.add_argument("--target-view-run-dir", type=Path, default=ROOT_DIR / "Backend/Benchmark/weak_labels/artifacts/phase_c/temporal_event_online_target_views_20260903_000725")
    parser.add_argument("--output-root", type=Path, default=ROOT_DIR / "Backend/Benchmark/model_suite/artifacts")
    parser.add_argument("--seed", type=int, default=20260717)
    parser.add_argument("--disruption-seed", type=int, default=20260921)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--max-lags", type=int, default=12)
    parser.add_argument("--cv-folds", nargs="+", default=["fold_01", "fold_02", "fold_03"])
    return parser


def main() -> None:
    args = build_parser().parse_args()
    snapshot_frame, snapshot_names, _ = load_feature_matrix(
        run_dir=args.snapshot_run_dir,
        view_id="v0_minimal_sensor",
    )
    window_frame, window_names, _ = load_feature_matrix(
        run_dir=args.window_run_dir,
        view_id="v2_sensor_row_window_3h",
    )
    row_index = pd.read_parquet(args.snapshot_run_dir.resolve() / "shared" / "row_index.parquet").convert_dtypes()
    snapshot_bundle = FeatureBundle(
        frame=snapshot_frame.loc[:, ["sample_id", *snapshot_names]].copy(),
        feature_names=snapshot_names,
        metadata={"representation": "snapshot", "future_used": False, "target_derived_features": False},
    )
    window_bundle = FeatureBundle(
        frame=window_frame.loc[:, ["sample_id", *window_names]].copy(),
        feature_names=window_names,
        metadata={"representation": "window_summaries", "future_used": False, "target_derived_features": False},
    )
    history_bundle = build_causal_history_bundle(
        snapshot_frame=snapshot_frame,
        snapshot_feature_names=snapshot_names,
        window_frame=window_frame,
        window_feature_names=window_names,
        row_index=row_index,
        max_lags=args.max_lags,
    )
    base_representations = build_representation_bundles(
        snapshot_bundle=snapshot_bundle,
        window_bundle=window_bundle,
        history_bundle=history_bundle,
    )
    audit_representations = build_history_audit_representations(
        representations=base_representations,
        disruption_seed=args.disruption_seed,
    )
    audit_representations["R11"] = base_representations["R11"]
    target_frame, target_metadata = load_online_event_target_frame(
        native_release_dir=args.native_release_dir,
        protocol_run_dir=args.protocol_run_dir,
        target_view_run_dir=args.target_view_run_dir,
    )
    run_id, output_dir = create_run_directory(args.output_root.resolve(), prefix="k_robustness_audit")
    single_variants = build_audit_variants(representations=audit_representations)
    single = run_single_fold_audit(
        variants=single_variants,
        target_frame=target_frame,
        output_dir=output_dir / "single_fold",
        random_seed=args.seed,
        thread_count=args.threads,
    )
    cv_variants = build_audit_variants(
        representations=audit_representations,
        representation_ids=("R01", "R11"),
    )
    assignment_path = args.protocol_run_dir.resolve() / "temporal_diagnostics" / "support_5day" / "view_effective_split_assignments.parquet"
    fold_frames, fold_support, fold_status = build_temporal_fold_frames(
        target_frame=target_frame,
        assignment_path=assignment_path,
        view_id="v2_temporal_3h",
        fold_ids=tuple(args.cv_folds),
    )
    cv = run_temporal_cv(
        variants=cv_variants,
        fold_frames=fold_frames,
        output_dir=output_dir / "cv",
        random_seed=args.seed,
        thread_count=args.threads,
    )
    cv["summary"] = summarize_cv_metrics(cv["metrics"])
    unres_audit = build_unres_audit(single["predictions"])
    oracle_rows = build_threshold_history_oracle(
        snapshot_frame=snapshot_frame,
        row_index=row_index,
        target_frame=target_frame,
        partition="test",
    )
    oracle_summary = summarize_threshold_oracle(oracle_rows)
    label_distribution = _label_distribution(target_frame)
    run_manifest = {
        "run_id": run_id,
        "artifact_type": "ROBUSTNESS_CLAIM_AUDIT_SUITE",
        "artifact_status": "ANALYSIS_ONLY",
        "model_key": "xgboost",
        "random_seed": args.seed,
        "disruption_seed": args.disruption_seed,
        "thread_count": args.threads,
        "primary_fold_policy": "E1_PRIMARY_7D_V1 / fold_01",
        "cv_policy": "support_5day effective assignments / selected folds",
        "cv_folds": list(args.cv_folds),
        "target_metadata": target_metadata,
        "feature_contract": {
            "future_forbidden_in_features": True,
            "support_depth_forbidden_in_features": True,
            "eventual_run_length_forbidden_in_features": True,
            "point_labels_forbidden_in_features": True,
            "provenance_strata_forbidden_in_features": True,
            "temporal_disruption": "per-row permutation of lag positions as nine-channel blocks",
            "representations": [
                {
                    "representation_id": representation_id,
                    "display_name": bundle.display_name,
                    "feature_count": len(bundle.feature_bundle.feature_names),
                    "sensor_lag_count": bundle.feature_bundle.metadata.get("sensor_lag_count", 0),
                    "metadata_count": bundle.feature_bundle.metadata.get("metadata_count", 0),
                    "summary_count": bundle.feature_bundle.metadata.get("summary_count", 0),
                    "ordered_addition_count": bundle.feature_bundle.metadata.get("ordered_addition_count", 0),
                    "temporal_order_disrupted": bool(bundle.feature_bundle.metadata.get("temporal_order_disrupted", False)),
                    "feature_names": bundle.feature_bundle.feature_names,
                }
                for representation_id, bundle in audit_representations.items()
            ],
        },
        "source_paths": {
            "snapshot_run_dir": str(args.snapshot_run_dir.resolve()),
            "window_run_dir": str(args.window_run_dir.resolve()),
            "native_release_dir": str(args.native_release_dir.resolve()),
            "protocol_run_dir": str(args.protocol_run_dir.resolve()),
            "target_view_run_dir": str(args.target_view_run_dir.resolve()),
            "cv_assignment_path": str(assignment_path),
        },
    }
    write_robustness_outputs(
        output_dir=output_dir,
        run_manifest=run_manifest,
        target_frame=target_frame,
        single=single,
        cv=cv,
        label_distribution=label_distribution,
        fold_support=fold_support,
        fold_status=fold_status,
        unres_audit=unres_audit,
        oracle_rows=oracle_rows,
        oracle_summary=oracle_summary,
    )
    print(
        json.dumps(
            {
                "run_id": run_id,
                "output_dir": str(output_dir),
                "single_metric_rows": len(single["metrics"]),
                "cv_metric_rows": len(cv["metrics"]),
                "cv_summary_rows": len(cv["summary"]),
                "unres_audit_rows": len(unres_audit),
                "oracle_rows": len(oracle_summary),
            },
            ensure_ascii=True,
        )
    )


def _label_distribution(target_frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    trainable = target_frame["final_trainability"].fillna(False).astype(bool)
    for target, label_column in (("online", "label_online"), ("event", "label_event")):
        for scope, mask in (
            ("eligible_pool", trainable),
            ("train", trainable & target_frame["partition"].astype("string").eq("train")),
            ("validation", trainable & target_frame["partition"].astype("string").eq("validation")),
            ("test", trainable & target_frame["partition"].astype("string").eq("test")),
        ):
            labels = target_frame.loc[mask, label_column].astype("string")
            for label_name, count in labels.value_counts(dropna=False).items():
                rows.append(
                    {
                        "target": target,
                        "scope": scope,
                        "label_name": str(label_name),
                        "count": int(count),
                        "share_pct": 100.0 * int(count) / len(labels) if len(labels) else float("nan"),
                        "scope_total": int(len(labels)),
                    }
                )
    return pd.DataFrame(rows).convert_dtypes()


if __name__ == "__main__":
    main()
