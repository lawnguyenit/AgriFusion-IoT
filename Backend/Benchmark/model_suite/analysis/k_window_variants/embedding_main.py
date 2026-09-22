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

from Backend.Benchmark.model_suite.analysis.k_window_variants.embedding import build_causal_sequence_bundle
from Backend.Benchmark.model_suite.analysis.k_window_variants.embedding_reporting import write_embedding_outputs
from Backend.Benchmark.model_suite.analysis.k_window_variants.embedding_runner import run_embedding_variants
from Backend.Benchmark.model_suite.analysis.k_window_variants.runner import load_feature_matrix
from Backend.Benchmark.model_suite.analysis.k_window_variants.semantic_targets import load_online_event_target_frame
from Backend.Benchmark.shared.artifacts import create_run_directory


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run causal GRU embedding to XGBoost K>1 probe.")
    parser.add_argument("--snapshot-run-dir", type=Path, default=ROOT_DIR / "Backend/Benchmark/dataset_views/artifacts/dataset_views_20260729_164926_756176")
    parser.add_argument("--native-release-dir", type=Path, default=ROOT_DIR / "Backend/Benchmark/weak_labels/artifacts/phase_c/native_engine_20260805_045419_359073")
    parser.add_argument("--protocol-run-dir", type=Path, default=ROOT_DIR / "Backend/Benchmark/evaluation_protocols/artifacts/evaluation_protocols_20260902_203645")
    parser.add_argument("--target-view-run-dir", type=Path, default=ROOT_DIR / "Backend/Benchmark/weak_labels/artifacts/phase_c/temporal_event_online_target_views_20260903_000725")
    parser.add_argument("--output-root", type=Path, default=ROOT_DIR / "Backend/Benchmark/model_suite/artifacts")
    parser.add_argument("--seed", type=int, default=20260717)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--sequence-length", type=int, default=12)
    parser.add_argument("--embedding-size", type=int, default=32)
    parser.add_argument("--max-epochs", type=int, default=120)
    parser.add_argument("--patience", type=int, default=18)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    snapshot_frame, feature_names, snapshot_manifest = load_feature_matrix(
        run_dir=args.snapshot_run_dir,
        view_id="v0_minimal_sensor",
    )
    row_index = pd.read_parquet(args.snapshot_run_dir.resolve() / "shared" / "row_index.parquet").convert_dtypes()
    sequence_bundle = build_causal_sequence_bundle(
        snapshot_frame=snapshot_frame,
        feature_names=feature_names,
        row_index=row_index,
        sequence_length=args.sequence_length,
    )
    target_frame, target_metadata = load_online_event_target_frame(
        native_release_dir=args.native_release_dir,
        protocol_run_dir=args.protocol_run_dir,
        target_view_run_dir=args.target_view_run_dir,
    )
    run_id, output_dir = create_run_directory(args.output_root.resolve(), prefix="k_gru_embedding")
    metrics, per_class, confusion, predictions, strata, embeddings = run_embedding_variants(
        sequence_bundle=sequence_bundle,
        target_frame=target_frame,
        output_dir=output_dir,
        random_seed=args.seed,
        thread_count=args.threads,
        embedding_size=args.embedding_size,
        max_epochs=args.max_epochs,
        patience=args.patience,
    )
    run_manifest = {
        "run_id": run_id,
        "artifact_type": "CAUSAL_GRU_EMBEDDING_TO_XGBOOST",
        "artifact_status": "ANALYSIS_ONLY",
        "model_key": "xgboost_after_causal_gru",
        "random_seed": args.seed,
        "thread_count": args.threads,
        "fold_policy": "E1_PRIMARY_7D_V1 / fold_01",
        "sequence_length": args.sequence_length,
        "embedding_size": args.embedding_size,
        "max_epochs": args.max_epochs,
        "patience": args.patience,
        "encoder_fit_partition": "train",
        "future_forbidden_in_features": True,
        "support_depth_forbidden_in_features": True,
        "eventual_run_length_forbidden_in_features": True,
        "target_metadata": target_metadata,
        "sequence_feature_names": feature_names,
        "sequence_contract": {
            "feature_count_per_step": len(feature_names),
            "input_channels": len(feature_names) * 2 + 2,
            "future_used": False,
            "includes_current_anchor": True,
            "history_horizon_seconds": sequence_bundle.horizon_seconds,
        },
        "source_paths": {
            "snapshot_run_dir": str(args.snapshot_run_dir.resolve()),
            "native_release_dir": str(args.native_release_dir.resolve()),
            "protocol_run_dir": str(args.protocol_run_dir.resolve()),
            "target_view_run_dir": str(args.target_view_run_dir.resolve()),
        },
        "source_manifest_hash": hashlib.sha256(
            (args.snapshot_run_dir.resolve() / "views" / "v0_minimal_sensor" / "manifest.json").read_bytes()
        ).hexdigest(),
    }
    write_embedding_outputs(
        output_dir=output_dir,
        run_manifest=run_manifest,
        metrics=metrics,
        per_class=per_class,
        confusion=confusion,
        predictions=predictions,
        strata=strata,
        embeddings=embeddings,
    )
    print(json.dumps({"run_id": run_id, "output_dir": str(output_dir), "metrics_rows": len(metrics), "stratum_rows": len(strata)}, ensure_ascii=True))


if __name__ == "__main__":
    main()
