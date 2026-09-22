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

from Backend.Benchmark.model_suite.analysis.k_window_variants.history import FeatureBundle, build_causal_history_bundle
from Backend.Benchmark.model_suite.analysis.k_window_variants.ordered_reporting import write_ordered_outputs
from Backend.Benchmark.model_suite.analysis.k_window_variants.ordered_representations import (
    ORDERED_REPRESENTATION_IDS,
    build_ordered_representation_bundles,
)
from Backend.Benchmark.model_suite.analysis.k_window_variants.representations import build_representation_bundles
from Backend.Benchmark.model_suite.analysis.k_window_variants.robustness_audit import (
    build_threshold_history_oracle,
    summarize_threshold_oracle,
)
from Backend.Benchmark.model_suite.analysis.k_window_variants.robustness_features import build_history_audit_representations
from Backend.Benchmark.model_suite.analysis.k_window_variants.runner import load_feature_matrix
from Backend.Benchmark.model_suite.analysis.k_window_variants.semantic_targets import load_online_event_target_frame
from Backend.Benchmark.model_suite.analysis.k_window_variants.configured_runner import ConfiguredVariant, run_configured_variants
from Backend.Benchmark.shared.artifacts import create_run_directory


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train Oracle -> M_t -> X_t -> M-history -> X-history -> X-history+context.")
    parser.add_argument("--snapshot-run-dir", type=Path, default=ROOT_DIR / "Backend/Benchmark/dataset_views/artifacts/dataset_views_20260729_164926_756176")
    parser.add_argument("--window-run-dir", type=Path, default=ROOT_DIR / "Backend/Benchmark/dataset_views/artifacts/dataset_views_20260729_164926_175188")
    parser.add_argument("--native-release-dir", type=Path, default=ROOT_DIR / "Backend/Benchmark/weak_labels/artifacts/phase_c/native_engine_20260805_045419_359073")
    parser.add_argument("--protocol-run-dir", type=Path, default=ROOT_DIR / "Backend/Benchmark/evaluation_protocols/artifacts/evaluation_protocols_20260902_203645")
    parser.add_argument("--target-view-run-dir", type=Path, default=ROOT_DIR / "Backend/Benchmark/weak_labels/artifacts/phase_c/temporal_event_online_target_views_20260903_000725")
    parser.add_argument("--output-root", type=Path, default=ROOT_DIR / "Backend/Benchmark/model_suite/artifacts")
    parser.add_argument("--seed", type=int, default=20260717)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--max-lags", type=int, default=12)
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
    ordered = build_ordered_representation_bundles(
        base_representations=base_representations,
        audit_representations=audit_representations,
    )
    target_frame, target_metadata = load_online_event_target_frame(
        native_release_dir=args.native_release_dir,
        protocol_run_dir=args.protocol_run_dir,
        target_view_run_dir=args.target_view_run_dir,
    )
    variants = _build_variants(ordered)
    run_id, output_dir = create_run_directory(args.output_root.resolve(), prefix="ordered_history_progression")
    metrics, per_class, confusion, predictions, strata = run_configured_variants(
        variants=variants,
        target_frame=target_frame,
        output_dir=output_dir,
        random_seed=args.seed,
        thread_count=args.threads,
    )
    oracle_rows = build_threshold_history_oracle(
        snapshot_frame=snapshot_frame,
        row_index=row_index,
        target_frame=target_frame,
        partition="test",
    )
    oracle_summary = summarize_threshold_oracle(oracle_rows)
    sequence = [
        {
            "order": 1,
            "stage": "Oracle",
            "trainable": False,
            "feature_count": 3,
            "definition": "direct M_t, M_t-1, M_t-2 threshold positive control",
        },
        {"order": 2, "stage": "M_t", "trainable": True, "feature_count": 1, "definition": "current soil moisture only"},
        {"order": 3, "stage": "X_t", "trainable": True, "feature_count": 9, "definition": "current nine-sensor snapshot"},
        {"order": 4, "stage": "M_history", "trainable": True, "feature_count": 13, "definition": "M_t plus 12 causal moisture lags"},
        {"order": 5, "stage": "X_history", "trainable": True, "feature_count": 117, "definition": "X_t plus 108 causal sensor lags"},
        {"order": 6, "stage": "X_history_context", "trainable": True, "feature_count": 162, "definition": "X-history plus 45 causal 3h context summaries; acquisition metadata excluded"},
    ]
    run_manifest = {
        "run_id": run_id,
        "artifact_type": "ORDERED_REPRESENTATION_PROGRESSION",
        "artifact_status": "ANALYSIS_ONLY",
        "model_key": "xgboost",
        "random_seed": args.seed,
        "thread_count": args.threads,
        "fold_policy": "E1_PRIMARY_7D_V1 / fold_01",
        "target_semantics": ["K3_ONLINE_CAUSAL", "K3_EVENT_RETROSPECTIVE"],
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
            for representation_id, bundle in ordered.items()
        },
        "target_metadata": target_metadata,
        "source_paths": {
            "snapshot_run_dir": str(args.snapshot_run_dir.resolve()),
            "window_run_dir": str(args.window_run_dir.resolve()),
            "native_release_dir": str(args.native_release_dir.resolve()),
            "protocol_run_dir": str(args.protocol_run_dir.resolve()),
            "target_view_run_dir": str(args.target_view_run_dir.resolve()),
        },
        "source_manifest_hashes": {
            "snapshot": _manifest_hash(args.snapshot_run_dir.resolve() / "views" / "v0_minimal_sensor" / "manifest.json"),
            "window": _manifest_hash(args.window_run_dir.resolve() / "views" / "v2_sensor_row_window_3h" / "manifest.json"),
        },
    }
    write_ordered_outputs(
        output_dir=output_dir,
        run_manifest=run_manifest,
        target_frame=target_frame,
        variants=variants,
        metrics=metrics,
        per_class=per_class,
        confusion=confusion,
        predictions=predictions,
        strata=strata,
        oracle_rows=oracle_rows,
        oracle_summary=oracle_summary,
    )
    print(json.dumps({"run_id": run_id, "output_dir": str(output_dir), "metrics_rows": len(metrics), "oracle_rows": len(oracle_summary)}, ensure_ascii=True))


def _build_variants(ordered: dict[str, object]) -> tuple[ConfiguredVariant, ...]:
    variants: list[ConfiguredVariant] = []
    for representation_id in ORDERED_REPRESENTATION_IDS:
        representation = ordered[representation_id]
        for target_view_id, semantics, label_column in (
            ("temporal_online_3h", "K3_ONLINE_CAUSAL", "label_online"),
            ("temporal_event_3h", "K3_EVENT_RETROSPECTIVE", "label_event"),
        ):
            variants.append(
                ConfiguredVariant(
                    variant_id=f"ordered_{representation_id}_{target_view_id.removeprefix('temporal_')}",
                    representation_id=representation_id,
                    target_view_id=target_view_id,
                    target_semantics=semantics,
                    k=3,
                    label_column=label_column,
                    representation=representation,
                )
            )
    return tuple(variants)


def _manifest_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    main()
