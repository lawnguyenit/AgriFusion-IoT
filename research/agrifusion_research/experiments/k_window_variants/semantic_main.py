from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[5]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from agrifusion_research.experiments.k_window_variants.history import build_causal_history_bundle
from agrifusion_research.experiments.k_window_variants.runner import load_feature_matrix
from agrifusion_research.experiments.k_window_variants.semantic_reporting import write_semantic_outputs
from agrifusion_research.experiments.k_window_variants.semantic_runner import build_semantic_variants, run_semantic_variants
from agrifusion_research.experiments.k_window_variants.semantic_targets import load_online_event_target_frame
from agrifusion_research.core.common.artifacts import create_run_directory
from agrifusion_research.core.common.digests import file_sha256
from agrifusion_research.core.common.paths import MODEL_SUITE_ROOT
from agrifusion_research.core.common.run_inputs import parse_with_run_inputs


# Required run directories; see experiments/k_window_variants/inputs.yaml for the runs used in 2026-09.
INPUT_KEYS = ("snapshot_run_dir", "window_run_dir", "native_release_dir", "protocol_run_dir", "target_view_run_dir",)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run causal-history K-online/K-event models with U_K provenance reporting.")
    parser.add_argument("--snapshot-run-dir", type=Path, default=None)
    parser.add_argument("--window-run-dir", type=Path, default=None)
    parser.add_argument("--native-release-dir", type=Path, default=None)
    parser.add_argument("--protocol-run-dir", type=Path, default=None)
    parser.add_argument("--target-view-run-dir", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, default=MODEL_SUITE_ROOT / "artifacts")
    parser.add_argument("--seed", type=int, default=20260717)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--max-lags", type=int, default=12)
    return parser


def main() -> None:
    args = parse_with_run_inputs(build_parser(), INPUT_KEYS)
    snapshot_frame, snapshot_names, snapshot_manifest = load_feature_matrix(
        run_dir=args.snapshot_run_dir,
        view_id="v0_minimal_sensor",
    )
    window_frame, window_names, window_manifest = load_feature_matrix(
        run_dir=args.window_run_dir,
        view_id="v2_sensor_row_window_3h",
    )
    row_index = pd.read_parquet(args.snapshot_run_dir.resolve() / "shared" / "row_index.parquet").convert_dtypes()
    snapshot_bundle = _snapshot_bundle(snapshot_frame, snapshot_names)
    history_bundle = build_causal_history_bundle(
        snapshot_frame=snapshot_frame,
        snapshot_feature_names=snapshot_names,
        window_frame=window_frame,
        window_feature_names=window_names,
        row_index=row_index,
        max_lags=args.max_lags,
    )
    target_frame, target_metadata = load_online_event_target_frame(
        native_release_dir=args.native_release_dir,
        protocol_run_dir=args.protocol_run_dir,
        target_view_run_dir=args.target_view_run_dir,
    )
    variants = build_semantic_variants(snapshot_bundle=snapshot_bundle, history_bundle=history_bundle)
    run_id, output_dir = create_run_directory(args.output_root.resolve(), prefix="k_history_semantics")
    metrics, per_class, confusion, predictions, strata = run_semantic_variants(
        variants=variants,
        target_frame=target_frame,
        output_dir=output_dir,
        random_seed=args.seed,
        thread_count=args.threads,
    )
    run_manifest = {
        "run_id": run_id,
        "artifact_type": "K_HISTORY_ONLINE_EVENT_SEMANTIC_BENCHMARK",
        "artifact_status": "ANALYSIS_ONLY",
        "model_key": "xgboost",
        "random_seed": args.seed,
        "thread_count": args.threads,
        "fold_policy": "E1_PRIMARY_7D_V1 / fold_01",
        "k": 3,
        "future_used_for": "Y_event label construction only",
        "future_forbidden_in_features": True,
        "support_depth_forbidden_in_features": True,
        "eventual_run_length_forbidden_in_features": True,
        "target_metadata": target_metadata,
        "feature_bundles": {
            "snapshot_9": {**snapshot_bundle.metadata, "feature_names": snapshot_bundle.feature_names},
            "causal_history_enriched_3h": {**history_bundle.metadata, "feature_names": history_bundle.feature_names},
        },
        "source_paths": {
            "snapshot_run_dir": str(args.snapshot_run_dir.resolve()),
            "window_run_dir": str(args.window_run_dir.resolve()),
            "native_release_dir": str(args.native_release_dir.resolve()),
            "protocol_run_dir": str(args.protocol_run_dir.resolve()),
            "target_view_run_dir": str(args.target_view_run_dir.resolve()),
        },
        "source_manifest_hashes": {
            "snapshot": file_sha256(args.snapshot_run_dir.resolve() / "views" / "v0_minimal_sensor" / "manifest.json"),
            "window": file_sha256(args.window_run_dir.resolve() / "views" / "v2_sensor_row_window_3h" / "manifest.json"),
        },
    }
    write_semantic_outputs(
        output_dir=output_dir,
        run_manifest=run_manifest,
        target_frame=target_frame,
        metrics=metrics,
        per_class=per_class,
        confusion=confusion,
        predictions=predictions,
        strata=strata,
    )
    print(json.dumps({"run_id": run_id, "output_dir": str(output_dir), "metrics_rows": len(metrics), "stratum_rows": len(strata)}, ensure_ascii=True))


def _snapshot_bundle(frame, feature_names):
    from agrifusion_research.experiments.k_window_variants.history import FeatureBundle

    return FeatureBundle(
        frame=frame.loc[:, ["sample_id", *feature_names]].copy(),
        feature_names=list(feature_names),
        metadata={
            "representation": "snapshot_9",
            "feature_count": len(feature_names),
            "future_used": False,
            "target_derived_features": False,
        },
    )


if __name__ == "__main__":
    main()
