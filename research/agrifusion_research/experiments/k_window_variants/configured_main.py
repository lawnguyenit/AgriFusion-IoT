from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


from agrifusion_research.experiments.k_window_variants.configured_reporting import write_configured_outputs
from agrifusion_research.experiments.k_window_variants.configured_runner import build_configured_variants, run_configured_variants
from agrifusion_research.experiments.k_window_variants.history import FeatureBundle, build_causal_history_bundle
from agrifusion_research.experiments.k_window_variants.representations import build_representation_bundles
from agrifusion_research.experiments.k_window_variants.runner import load_feature_matrix
from agrifusion_research.experiments.k_window_variants.semantic_targets import load_online_event_target_frame
from agrifusion_research.core.common.artifacts import create_run_directory
from agrifusion_research.core.common.digests import file_sha256
from agrifusion_research.core.common.paths import MODEL_SUITE_ROOT
from agrifusion_research.core.common.run_inputs import parse_with_run_inputs


# Required run directories; see experiments/k_window_variants/inputs.yaml for the runs used in 2026-09.
INPUT_KEYS = ("snapshot_run_dir", "window_run_dir", "native_release_dir", "protocol_run_dir", "target_view_run_dir",)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run configured R00/R10/R01/R11 K1/K3 benchmark.")
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
    representations = build_representation_bundles(
        snapshot_bundle=snapshot_bundle,
        window_bundle=window_bundle,
        history_bundle=history_bundle,
    )
    k1_frame, k1_metadata = _load_k1_frame(
        native_release_dir=args.native_release_dir,
        protocol_run_dir=args.protocol_run_dir,
    )
    k3_frame, k3_metadata = load_online_event_target_frame(
        native_release_dir=args.native_release_dir,
        protocol_run_dir=args.protocol_run_dir,
        target_view_run_dir=args.target_view_run_dir,
    )
    if "label_k1" in k3_frame.columns:
        target_frame = k3_frame.copy()
        if not target_frame["label_k1"].astype("string").equals(k1_frame.set_index("sample_id").loc[target_frame["sample_id"], "label_k1"].reset_index(drop=True)):
            raise ValueError("K1 labels in the paired target frame disagree with the independently loaded K1 frame.")
    else:
        target_frame = k3_frame.merge(
            k1_frame.loc[:, ["sample_id", "label_k1"]],
            on="sample_id",
            how="left",
            validate="one_to_one",
        )
    if target_frame["label_k1"].isna().any():
        raise ValueError("Configured benchmark target frame is missing K1 labels.")
    variants = build_configured_variants(representations=representations)
    run_id, output_dir = create_run_directory(args.output_root.resolve(), prefix="k_configured_r_matrix")
    metrics, per_class, confusion, predictions, strata = run_configured_variants(
        variants=variants,
        target_frame=target_frame,
        output_dir=output_dir,
        random_seed=args.seed,
        thread_count=args.threads,
    )
    representation_contract = {
        "R00": "snapshot: nine current sensor attributes",
        "R10": "window summaries: R00 plus 45 causal 3h summary statistics",
        "R01": "ordered flatten: R00 plus 108 strictly-past lags, 12 lag ages, and 5 history-quality fields",
        "R11": "window plus ordered flatten: R10 plus the ordered additions from R01",
        "future_forbidden_in_features": True,
        "support_depth_forbidden_in_features": True,
        "eventual_run_length_forbidden_in_features": True,
        "point_labels_forbidden_in_features": True,
        "provenance_strata_forbidden_in_features": True,
        "representations": [
            {
                "representation_id": representation_id,
                "display_name": bundle.display_name,
                "feature_count": len(bundle.feature_bundle.feature_names),
                "summary_count": bundle.feature_bundle.metadata.get("summary_count", 0),
                "ordered_addition_count": bundle.feature_bundle.metadata.get("ordered_addition_count", 0),
                "feature_names": bundle.feature_bundle.feature_names,
            }
            for representation_id, bundle in representations.items()
        ],
    }
    schedule = [
        {
            "variant_id": variant.variant_id,
            "target_view_id": variant.target_view_id,
            "target_semantics": variant.target_semantics,
            "k": variant.k,
            "representation_id": variant.representation_id,
            "feature_count": len(variant.representation.feature_bundle.feature_names),
        }
        for variant in variants
    ]
    run_manifest = {
        "run_id": run_id,
        "artifact_type": "CONFIGURED_R00_R10_R01_R11_K_BENCHMARK",
        "artifact_status": "ANALYSIS_ONLY",
        "model_key": "xgboost",
        "random_seed": args.seed,
        "thread_count": args.threads,
        "fold_policy": "E1_PRIMARY_7D_V1 / fold_01",
        "schedule": schedule,
        "representation_contract": representation_contract,
        "target_metadata": {"k1": k1_metadata, "k3_online_event": k3_metadata},
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
    write_configured_outputs(
        output_dir=output_dir,
        run_manifest=run_manifest,
        target_frame=target_frame,
        variants=variants,
        metrics=metrics,
        per_class=per_class,
        confusion=confusion,
        predictions=predictions,
        strata=strata,
    )
    print(json.dumps({"run_id": run_id, "output_dir": str(output_dir), "variant_count": len(variants), "metrics_rows": len(metrics), "stratum_rows": len(strata)}, ensure_ascii=True))


def _load_k1_frame(*, native_release_dir: Path, protocol_run_dir: Path) -> tuple[pd.DataFrame, dict[str, object]]:
    from agrifusion_research.experiments.k_window_variants.targets import load_temporal_target_frame

    return load_temporal_target_frame(native_release_dir=native_release_dir, protocol_run_dir=protocol_run_dir)


if __name__ == "__main__":
    main()
