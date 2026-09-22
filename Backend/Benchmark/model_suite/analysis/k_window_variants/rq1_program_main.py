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
from Backend.Benchmark.model_suite.analysis.k_window_variants.robustness_runner import build_temporal_fold_frames, run_temporal_cv, summarize_cv_metrics
from Backend.Benchmark.model_suite.analysis.k_window_variants.rq1_program_reporting import write_program_outputs
from Backend.Benchmark.model_suite.analysis.k_window_variants.rq1_program_representations import (
    CORE_IDS,
    PROBE_IDS,
    PROBE_LABELS,
    add_persistence_probe_target,
    build_program_representations,
)
from Backend.Benchmark.model_suite.analysis.k_window_variants.rq1_program_runner import ProbeVariant, run_probe_temporal_cv, summarize_probe_metrics
from Backend.Benchmark.model_suite.analysis.k_window_variants.rq1_program_statistics import build_factorial_contrasts, build_module_a_group_metrics, build_snapshot_alias_pairs
from Backend.Benchmark.model_suite.analysis.k_window_variants.rq1_statistics import add_temporal_order_columns, build_paired_contrasts, build_per_anchor_losses
from Backend.Benchmark.model_suite.analysis.k_window_variants.runner import load_feature_matrix
from Backend.Benchmark.model_suite.analysis.k_window_variants.semantic_targets import load_online_event_target_frame
from Backend.Benchmark.shared.artifacts import create_run_directory


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the structured RQ1 experimental program.")
    parser.add_argument("--snapshot-run-dir", type=Path, default=ROOT_DIR / "Backend/Benchmark/dataset_views/artifacts/dataset_views_20260729_164926_756176")
    parser.add_argument("--window-run-dir", type=Path, default=ROOT_DIR / "Backend/Benchmark/dataset_views/artifacts/dataset_views_20260729_164926_175188")
    parser.add_argument("--native-release-dir", type=Path, default=ROOT_DIR / "Backend/Benchmark/weak_labels/artifacts/phase_c/native_engine_20260805_045419_359073")
    parser.add_argument("--protocol-run-dir", type=Path, default=ROOT_DIR / "Backend/Benchmark/evaluation_protocols/artifacts/evaluation_protocols_20260902_203645")
    parser.add_argument("--target-view-run-dir", type=Path, default=ROOT_DIR / "Backend/Benchmark/weak_labels/artifacts/phase_c/temporal_event_online_target_views_20260903_000725")
    parser.add_argument("--output-root", type=Path, default=ROOT_DIR / "Backend/Benchmark/model_suite/artifacts")
    parser.add_argument("--seed", type=int, default=20260717)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--max-lags", type=int, default=12)
    parser.add_argument("--cv-folds", nargs="+", default=["fold_01", "fold_02", "fold_03"])
    parser.add_argument("--block-length", type=int, default=12)
    parser.add_argument("--bootstrap-reps", type=int, default=1000)
    parser.add_argument("--alias-epsilon", type=float, default=0.21)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    snapshot_frame, snapshot_names, snapshot_manifest = load_feature_matrix(run_dir=args.snapshot_run_dir, view_id="v0_minimal_sensor")
    window_frame, window_names, window_manifest = load_feature_matrix(run_dir=args.window_run_dir, view_id="v2_sensor_row_window_3h")
    row_index = pd.read_parquet(args.snapshot_run_dir.resolve() / "shared" / "row_index.parquet").convert_dtypes()
    window_audit = pd.read_parquet(args.window_run_dir.resolve() / "views" / "v2_sensor_row_window_3h" / "window_quality_audit.parquet").convert_dtypes()
    snapshot_bundle = FeatureBundle(snapshot_frame.loc[:, ["sample_id", *snapshot_names]].copy(), snapshot_names, {"representation": "snapshot"})
    window_bundle = FeatureBundle(window_frame.loc[:, ["sample_id", *window_names]].copy(), window_names, {"representation": "window_summaries"})
    history_bundle = build_causal_history_bundle(snapshot_frame=snapshot_frame, snapshot_feature_names=snapshot_names, window_frame=window_frame, window_feature_names=window_names, row_index=row_index, max_lags=args.max_lags)
    base = build_representation_bundles(snapshot_bundle=snapshot_bundle, window_bundle=window_bundle, history_bundle=history_bundle)
    from Backend.Benchmark.model_suite.analysis.k_window_variants.robustness_features import build_history_audit_representations
    from Backend.Benchmark.model_suite.analysis.k_window_variants.rq1_representations import build_rq1_nested_representations
    audit = build_history_audit_representations(representations=base, disruption_seed=args.seed)
    nested = build_rq1_nested_representations(base_representations=base, audit_representations=audit)
    program = build_program_representations(snapshot_bundle=snapshot_bundle, window_bundle=window_bundle, history_bundle=history_bundle, nested=nested, row_index=row_index, window_audit=window_audit, negative_seed=args.seed)
    target_frame, target_metadata = load_online_event_target_frame(native_release_dir=args.native_release_dir, protocol_run_dir=args.protocol_run_dir, target_view_run_dir=args.target_view_run_dir)
    target_frame = add_persistence_probe_target(target_frame)
    assignment_path = args.protocol_run_dir.resolve() / "temporal_diagnostics" / "support_5day" / "view_effective_split_assignments.parquet"
    fold_frames, fold_support, fold_status = build_temporal_fold_frames(target_frame=target_frame, assignment_path=assignment_path, view_id="v2_temporal_3h", fold_ids=tuple(args.cv_folds))
    run_id, output_dir = create_run_directory(args.output_root.resolve(), prefix="rq1_structured_program")

    primary_variants = _build_primary_variants(program.representations)
    primary_cv = run_temporal_cv(variants=primary_variants, fold_frames=fold_frames, output_dir=output_dir / "primary_cv", random_seed=args.seed, thread_count=args.threads)
    primary_summary = summarize_cv_metrics(primary_cv["metrics"])
    aligned_predictions = add_temporal_order_columns(primary_cv["predictions"], row_index)
    primary_losses = build_per_anchor_losses(aligned_predictions)
    primary_contrasts = _build_primary_contrasts(primary_losses, args)
    factorial_by_fold, factorial_summary = build_factorial_contrasts(losses=primary_losses, block_length=args.block_length, bootstrap_reps=args.bootstrap_reps, seed=args.seed)

    moisture_frame = snapshot_frame.loc[:, ["sample_id", MOISTURE]].rename(columns={MOISTURE: "moisture_current"})
    module_a_groups = build_module_a_group_metrics(predictions=aligned_predictions, target_frame=target_frame, row_index=row_index, moisture_frame=moisture_frame)
    alias_anchors = _build_alias_anchors(target_frame=target_frame, row_index=row_index, moisture_frame=moisture_frame, fold_frames=fold_frames)
    alias_pairs, alias_summary = build_snapshot_alias_pairs(anchors=alias_anchors, epsilon=args.alias_epsilon)

    probe_variants = tuple(ProbeVariant(variant_id=f"probe_{representation_id}", representation_id=representation_id, representation=program.representations[representation_id], label_column="persistence_state", class_names=PROBE_LABELS) for representation_id in PROBE_IDS)
    probe = run_probe_temporal_cv(variants=probe_variants, fold_frames=fold_frames, output_dir=output_dir / "persistence_probe", random_seed=args.seed, thread_count=args.threads)
    probe_summary = summarize_probe_metrics(probe["metrics"])

    manifest = _build_manifest(args=args, run_id=run_id, output_dir=output_dir, program=program, target_metadata=target_metadata, assignment_path=assignment_path, snapshot_manifest=snapshot_manifest, window_manifest=window_manifest, primary_variants=primary_variants, probe_variants=probe_variants, fold_status=fold_status)
    write_program_outputs(output_dir=output_dir, run_manifest=manifest, target_frame=target_frame, primary_cv=primary_cv, primary_summary=primary_summary, primary_losses=primary_losses, primary_contrasts=primary_contrasts, factorial_by_fold=factorial_by_fold, factorial_summary=factorial_summary, module_a_groups=module_a_groups, alias_pairs=alias_pairs, alias_summary=alias_summary, probe=probe, probe_summary=probe_summary)
    print(json.dumps({"run_id": run_id, "output_dir": str(output_dir), "primary_variant_count": len(primary_variants), "primary_metric_rows": len(primary_cv["metrics"]), "primary_prediction_rows": len(primary_cv["predictions"]), "factorial_rows": len(factorial_summary), "alias_pairs": len(alias_pairs), "probe_metric_rows": len(probe["metrics"])}, ensure_ascii=True))


def _build_primary_variants(representations: dict[str, object]) -> tuple[ConfiguredVariant, ...]:
    variants: list[ConfiguredVariant] = []
    for representation_id in CORE_IDS:
        representation = representations[representation_id]
        for target_view_id, semantics, label_column in (("temporal_online_3h", "K3_ONLINE_CAUSAL", "label_online"), ("temporal_event_3h", "K3_EVENT_RETROSPECTIVE", "label_event")):
            variants.append(ConfiguredVariant(variant_id=f"program_{representation_id}_{target_view_id.removeprefix('temporal_')}", representation_id=representation_id, target_view_id=target_view_id, target_semantics=semantics, k=3, label_column=label_column, representation=representation))
    return tuple(variants)


def _build_primary_contrasts(losses: pd.DataFrame, args: argparse.Namespace) -> pd.DataFrame:
    arrows = (
        ("S0_to_S1", "S0_M_t", "S1_X_t"),
        ("B_M_to_S2_same_C", "B_M", "S2_X_t_HM"),
        ("F00_to_F10_add_HX", "S1_X_t", "S3_X_t_HX"),
        ("F00_to_F01_add_WX", "S1_X_t", "F01_X_t_WX"),
        ("F00_to_F11_add_HX_WX", "S1_X_t", "F11_X_t_HX_WX"),
        ("S3_to_S3T_add_T", "S3_X_t_HX", "S3_X_HX_T"),
        ("F11_to_F11T_add_T", "F11_X_t_HX_WX", "F11_X_HX_WX_T"),
        ("S3_to_S3A_add_A", "S3_X_t_HX", "S3_X_HX_A"),
        ("S3_to_S3N45", "S3_X_t_HX", "S3_X_HX_N45"),
    )
    _, summary = build_paired_contrasts(losses=losses, arrows=arrows, block_length=args.block_length, bootstrap_reps=args.bootstrap_reps, seed=args.seed)
    return summary


def _build_alias_anchors(*, target_frame: pd.DataFrame, row_index: pd.DataFrame, moisture_frame: pd.DataFrame, fold_frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    ids = pd.concat([frame.loc[frame["partition"].astype("string").eq("test"), ["sample_id"]] for frame in fold_frames.values()], ignore_index=True).drop_duplicates("sample_id")
    metadata = target_frame.merge(ids, on="sample_id", how="inner", validate="one_to_one")
    metadata = metadata.loc[:, ["sample_id", "support_depth_at_anchor", "label_online", "label_event"]]
    metadata = metadata.merge(moisture_frame, on="sample_id", how="inner", validate="one_to_one")
    ordered = row_index.rename(columns={"record.id": "sample_id"}).loc[:, ["sample_id", "record.node_id", "record.segment_id", "record.ts_sample"]]
    return metadata.merge(ordered, on="sample_id", how="inner", validate="one_to_one").convert_dtypes()


def _build_manifest(*, args: argparse.Namespace, run_id: str, output_dir: Path, program, target_metadata: dict[str, object], assignment_path: Path, snapshot_manifest: dict[str, object], window_manifest: dict[str, object], primary_variants: tuple[ConfiguredVariant, ...], probe_variants: tuple[ProbeVariant, ...], fold_status: dict[str, dict[str, object]]) -> dict[str, object]:
    schedule: list[dict[str, object]] = []
    for variant in primary_variants:
        schedule.append({"module": "primary_A_B_D_E_F_negative", "condition": variant.representation_id, "representation_id": variant.representation_id, "feature_count": len(variant.representation.feature_bundle.feature_names), "target": variant.target_view_id})
    for variant in probe_variants:
        schedule.append({"module": "C_persistence_probe", "condition": variant.representation_id, "representation_id": variant.representation_id, "feature_count": len(variant.representation.feature_bundle.feature_names), "target": "persistence_state_d_clip_3"})
    return {
        "run_id": run_id,
        "artifact_type": "RQ1_STRUCTURED_EXPERIMENTAL_PROGRAM",
        "artifact_status": "ANALYSIS_ONLY",
        "model_key": "xgboost",
        "random_seed": args.seed,
        "thread_count": args.threads,
        "cv_folds": list(args.cv_folds),
        "fold_status": fold_status,
        "block_contract": program.block_contract,
        "program_schedule": schedule,
        "module_definitions": {
            "A": "S0 group error on G0/G1/G2 plus same-current-moisture alias pairs",
            "B": "S0->S1 and B_M->S2 paired added-C contrasts",
            "C": "diagnostic d clipped to K=3 persistence-state probe",
            "D": "F00/F10/F01/F11 2x2 raw-lag x engineered-window factorial",
            "E": "S3/F11 versus adding timestamp-age-gap-continuity T",
            "F": "A-only and S3+A acquisition/quality shortcut controls",
            "negative_control": "S3 plus label-independent 45-dimensional permuted W block",
        },
        "primary_loss": "multiclass log loss on paired held-out anchors",
        "secondary_losses": ["multiclass Brier loss"],
        "pr_metric_definition": "macro one-vs-rest Average Precision from one-hot labels using sklearn average_precision_score average=macro; not trapezoidal PR area",
        "bootstrap": {"block_length": args.block_length, "repetitions": args.bootstrap_reps, "grouping": ["fold_id", "record.node_id", "record.segment_id"], "seed": args.seed},
        "alias_epsilon": args.alias_epsilon,
        "target_metadata": target_metadata,
        "source_paths": {"snapshot_run_dir": str(args.snapshot_run_dir.resolve()), "window_run_dir": str(args.window_run_dir.resolve()), "native_release_dir": str(args.native_release_dir.resolve()), "protocol_run_dir": str(args.protocol_run_dir.resolve()), "target_view_run_dir": str(args.target_view_run_dir.resolve()), "assignment_path": str(assignment_path), "output_dir": str(output_dir.resolve())},
        "source_manifest_hashes": {"snapshot": _manifest_hash(args.snapshot_run_dir.resolve() / "views" / "v0_minimal_sensor" / "manifest.json"), "window": _manifest_hash(args.window_run_dir.resolve() / "views" / "v2_sensor_row_window_3h" / "manifest.json")},
        "source_feature_manifests": {"snapshot": snapshot_manifest, "window": window_manifest},
    }


def _manifest_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


MOISTURE = "npk.soil_moisture_pct"


if __name__ == "__main__":
    main()
