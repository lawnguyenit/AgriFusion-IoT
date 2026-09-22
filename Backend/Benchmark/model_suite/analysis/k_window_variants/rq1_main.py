from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[5]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from Backend.Benchmark.model_suite.analysis.k_window_variants.configured_runner import ConfiguredVariant
from Backend.Benchmark.model_suite.analysis.k_window_variants.history import FeatureBundle, build_causal_history_bundle
from Backend.Benchmark.model_suite.analysis.k_window_variants.representations import build_representation_bundles
from Backend.Benchmark.model_suite.analysis.k_window_variants.robustness_audit import (
    build_threshold_history_oracle,
    summarize_threshold_oracle,
)
from Backend.Benchmark.model_suite.analysis.k_window_variants.robustness_features import build_history_audit_representations
from Backend.Benchmark.model_suite.analysis.k_window_variants.robustness_runner import (
    build_temporal_fold_frames,
    run_temporal_cv,
    summarize_cv_metrics,
)
from Backend.Benchmark.model_suite.analysis.k_window_variants.rq1_reporting import write_rq1_outputs
from Backend.Benchmark.model_suite.analysis.k_window_variants.rq1_representations import (
    RQ1_BRANCH_ID,
    RQ1_MAIN_IDS,
    build_rq1_nested_representations,
)
from Backend.Benchmark.model_suite.analysis.k_window_variants.rq1_statistics import (
    add_temporal_order_columns,
    build_paired_contrasts,
    build_per_anchor_losses,
)
from Backend.Benchmark.model_suite.analysis.k_window_variants.runner import load_feature_matrix
from Backend.Benchmark.model_suite.analysis.k_window_variants.semantic_targets import load_online_event_target_frame
from Backend.Benchmark.shared.artifacts import create_run_directory


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the corrected nested RQ1 information progression with paired risk contrasts."
    )
    parser.add_argument(
        "--snapshot-run-dir",
        type=Path,
        default=ROOT_DIR / "Backend/Benchmark/dataset_views/artifacts/dataset_views_20260729_164926_756176",
    )
    parser.add_argument(
        "--window-run-dir",
        type=Path,
        default=ROOT_DIR / "Backend/Benchmark/dataset_views/artifacts/dataset_views_20260729_164926_175188",
    )
    parser.add_argument(
        "--native-release-dir",
        type=Path,
        default=ROOT_DIR / "Backend/Benchmark/weak_labels/artifacts/phase_c/native_engine_20260805_045419_359073",
    )
    parser.add_argument(
        "--protocol-run-dir",
        type=Path,
        default=ROOT_DIR / "Backend/Benchmark/evaluation_protocols/artifacts/evaluation_protocols_20260902_203645",
    )
    parser.add_argument(
        "--target-view-run-dir",
        type=Path,
        default=ROOT_DIR / "Backend/Benchmark/weak_labels/artifacts/phase_c/temporal_event_online_target_views_20260903_000725",
    )
    parser.add_argument("--output-root", type=Path, default=ROOT_DIR / "Backend/Benchmark/model_suite/artifacts")
    parser.add_argument("--seed", type=int, default=20260717)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--max-lags", type=int, default=12)
    parser.add_argument("--cv-folds", nargs="+", default=["fold_01", "fold_02", "fold_03"])
    parser.add_argument("--block-length", type=int, default=12)
    parser.add_argument("--bootstrap-reps", type=int, default=1000)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    snapshot_frame, snapshot_names, snapshot_manifest = load_feature_matrix(
        run_dir=args.snapshot_run_dir,
        view_id="v0_minimal_sensor",
    )
    window_frame, window_names, window_manifest = load_feature_matrix(
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
        disruption_seed=args.seed,
    )
    nested = build_rq1_nested_representations(
        base_representations=base_representations,
        audit_representations=audit_representations,
    )
    target_frame, target_metadata = load_online_event_target_frame(
        native_release_dir=args.native_release_dir,
        protocol_run_dir=args.protocol_run_dir,
        target_view_run_dir=args.target_view_run_dir,
    )
    assignment_path = args.protocol_run_dir.resolve() / "temporal_diagnostics" / "support_5day" / "view_effective_split_assignments.parquet"
    fold_frames, fold_support, fold_status = build_temporal_fold_frames(
        target_frame=target_frame,
        assignment_path=assignment_path,
        view_id="v2_temporal_3h",
        fold_ids=tuple(args.cv_folds),
    )
    variants = _build_variants(nested)
    run_id, output_dir = create_run_directory(args.output_root.resolve(), prefix="rq1_nested_progression")
    cv = run_temporal_cv(
        variants=variants,
        fold_frames=fold_frames,
        output_dir=output_dir / "cv",
        random_seed=args.seed,
        thread_count=args.threads,
    )
    cv_summary = summarize_cv_metrics(cv["metrics"])
    aligned_predictions = add_temporal_order_columns(cv["predictions"], row_index)
    losses = build_per_anchor_losses(aligned_predictions)
    fold_contrasts, contrast_summary = build_paired_contrasts(
        losses=losses,
        arrows=(
            ("S0_to_S1", "S0_M_t", "S1_X_t"),
            ("S1_to_S2", "S1_X_t", "S2_X_t_HM"),
            ("S2_to_S3", "S2_X_t_HM", "S3_X_t_HX"),
            ("S3_to_S4", "S3_X_t_HX", "S4_X_t_HX_C"),
            ("B_M_vs_S0", "S0_M_t", RQ1_BRANCH_ID),
        ),
        block_length=args.block_length,
        bootstrap_reps=args.bootstrap_reps,
        seed=args.seed,
    )
    oracle_rows, oracle_summary = _build_fold_oracle_rows(
        snapshot_frame=snapshot_frame,
        row_index=row_index,
        fold_frames=fold_frames,
    )
    sequence = _sequence_contract(nested)
    run_manifest = {
        "run_id": run_id,
        "artifact_type": "RQ1_NESTED_INFORMATION_PROGRESSION",
        "artifact_status": "ANALYSIS_ONLY",
        "model_key": "xgboost",
        "random_seed": args.seed,
        "thread_count": args.threads,
        "cv_folds": list(args.cv_folds),
        "cv_assignment_path": str(assignment_path),
        "target_semantics": ["K3_ONLINE_CAUSAL", "K3_EVENT_RETROSPECTIVE"],
        "pr_metric_definition": "macro one-vs-rest Average Precision: sklearn average_precision_score on one-hot labels with average=macro; not trapezoidal PR area",
        "primary_loss": "multiclass log loss computed from held-out three-class probabilities",
        "secondary_loss": "multiclass Brier loss, sum of squared one-hot probability errors",
        "paired_contrast_definition": "delta = loss(previous information set) - loss(next information set); positive means lower loss after adding information",
        "block_bootstrap": {
            "block_length": args.block_length,
            "repetitions": args.bootstrap_reps,
            "grouping": ["fold_id", "record.node_id", "record.segment_id"],
            "seed": args.seed,
            "method": "circular moving temporal blocks within node/segment groups",
        },
        "sequence": sequence,
        "representation_contract": {
            representation_id: {
                "display_name": bundle.display_name,
                "feature_count": len(bundle.feature_bundle.feature_names),
                "feature_groups": bundle.feature_bundle.metadata.get("feature_groups", {}),
                "future_used": False,
                "target_derived_features": False,
                "acquisition_metadata_included": False,
                "feature_names": bundle.feature_bundle.feature_names,
            }
            for representation_id, bundle in nested.items()
        },
        "target_metadata": target_metadata,
        "source_paths": {
            "snapshot_run_dir": str(args.snapshot_run_dir.resolve()),
            "window_run_dir": str(args.window_run_dir.resolve()),
            "native_release_dir": str(args.native_release_dir.resolve()),
            "protocol_run_dir": str(args.protocol_run_dir.resolve()),
            "target_view_run_dir": str(args.target_view_run_dir.resolve()),
            "cv_assignment_path": str(assignment_path),
        },
        "source_manifest_hashes": {
            "snapshot": _manifest_hash(args.snapshot_run_dir.resolve() / "views" / "v0_minimal_sensor" / "manifest.json"),
            "window": _manifest_hash(args.window_run_dir.resolve() / "views" / "v2_sensor_row_window_3h" / "manifest.json"),
        },
        "source_feature_manifests": {
            "snapshot": snapshot_manifest,
            "window": window_manifest,
        },
    }
    write_rq1_outputs(
        output_dir=output_dir,
        run_manifest=run_manifest,
        target_frame=target_frame,
        variants=variants,
        cv=cv,
        cv_summary=cv_summary,
        fold_support=fold_support,
        fold_status=fold_status,
        losses=losses,
        fold_contrasts=fold_contrasts,
        contrast_summary=contrast_summary,
        oracle_rows=oracle_rows,
        oracle_summary=oracle_summary,
    )
    print(
        json.dumps(
            {
                "run_id": run_id,
                "output_dir": str(output_dir),
                "variant_count": len(variants),
                "cv_metric_rows": len(cv["metrics"]),
                "prediction_rows": len(cv["predictions"]),
                "contrast_rows": len(contrast_summary),
                "oracle_rows": len(oracle_summary),
            },
            ensure_ascii=True,
        )
    )


def _build_variants(nested: dict[str, object]) -> tuple[ConfiguredVariant, ...]:
    variants: list[ConfiguredVariant] = []
    for representation_id in (*RQ1_MAIN_IDS, RQ1_BRANCH_ID):
        representation = nested[representation_id]
        for target_view_id, semantics, label_column in (
            ("temporal_online_3h", "K3_ONLINE_CAUSAL", "label_online"),
            ("temporal_event_3h", "K3_EVENT_RETROSPECTIVE", "label_event"),
        ):
            variants.append(
                ConfiguredVariant(
                    variant_id=f"rq1_{representation_id}_{target_view_id.removeprefix('temporal_')}",
                    representation_id=representation_id,
                    target_view_id=target_view_id,
                    target_semantics=semantics,
                    k=3,
                    label_column=label_column,
                    representation=representation,
                )
            )
    return tuple(variants)


def _build_fold_oracle_rows(
    *,
    snapshot_frame: pd.DataFrame,
    row_index: pd.DataFrame,
    fold_frames: dict[str, pd.DataFrame],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[pd.DataFrame] = []
    summaries: list[pd.DataFrame] = []
    for fold_id, fold_target in fold_frames.items():
        fold_rows = build_threshold_history_oracle(
            snapshot_frame=snapshot_frame,
            row_index=row_index,
            target_frame=fold_target,
            partition="test",
        )
        if fold_rows.empty:
            continue
        fold_rows.insert(0, "fold_id", fold_id)
        fold_summary = summarize_threshold_oracle(fold_rows)
        fold_summary.insert(0, "fold_id", fold_id)
        rows.append(fold_rows)
        summaries.append(fold_summary)
    return _concat(rows), _concat(summaries)


def _sequence_contract(nested: dict[str, object]) -> list[dict[str, object]]:
    definitions = {
        "S0_M_t": "current soil moisture only",
        "S1_X_t": "current nine-sensor snapshot",
        "S2_X_t_HM": "S1 plus 12 strictly-past moisture lags",
        "S3_X_t_HX": "S1 plus 108 strictly-past lags for all nine sensors",
        "S4_X_t_HX_C": "S3 plus 45 causal 3h context summaries",
        "B_M": "diagnostic branch: current moisture plus 12 strictly-past moisture lags",
    }
    rows: list[dict[str, object]] = []
    for order, representation_id in enumerate(RQ1_MAIN_IDS):
        bundle = nested[representation_id]
        rows.append(
            {
                "order": order,
                "stage": representation_id,
                "role": "main_chain",
                "feature_count": len(bundle.feature_bundle.feature_names),
                "definition": definitions[representation_id],
            }
        )
    branch = nested[RQ1_BRANCH_ID]
    rows.append(
        {
            "order": "diagnostic",
            "stage": RQ1_BRANCH_ID,
            "role": "diagnostic_branch",
            "feature_count": len(branch.feature_bundle.feature_names),
            "definition": definitions[RQ1_BRANCH_ID],
        }
    )
    return rows


def _concat(frames: list[pd.DataFrame]) -> pd.DataFrame:
    nonempty = [frame for frame in frames if not frame.empty]
    if not nonempty:
        return pd.DataFrame()
    return pd.concat(nonempty, ignore_index=True).convert_dtypes()


def _manifest_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    main()
