from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[5]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from Backend.Benchmark.model_suite.analysis.k_window_variants.configured_runner import ConfiguredVariant
from Backend.Benchmark.model_suite.analysis.k_window_variants.history import FeatureBundle, build_causal_history_bundle
from Backend.Benchmark.model_suite.analysis.k_window_variants.robustness_runner import build_temporal_fold_frames, run_temporal_cv, summarize_cv_metrics
from Backend.Benchmark.model_suite.analysis.k_window_variants.rq1_program_representations import REVIEW_IDS, build_program_representations
from Backend.Benchmark.model_suite.analysis.k_window_variants.rq1_statistics import add_temporal_order_columns, build_paired_contrasts, build_per_anchor_losses
from Backend.Benchmark.model_suite.analysis.k_window_variants.runner import REPORT_LABELS, load_feature_matrix
from Backend.Benchmark.model_suite.analysis.k_window_variants.rq1_program_representations import add_persistence_probe_target
from Backend.Benchmark.model_suite.analysis.k_window_variants.rq1_representations import build_rq1_nested_representations
from Backend.Benchmark.model_suite.analysis.k_window_variants.robustness_features import build_history_audit_representations
from Backend.Benchmark.model_suite.analysis.k_window_variants.representations import build_representation_bundles
from Backend.Benchmark.model_suite.analysis.k_window_variants.semantic_targets import load_online_event_target_frame
from Backend.Benchmark.model_suite.analysis.k_window_variants.targets import AUX_POINT, LOW_POINT, REF_POINT, LOW_TEMPORAL, REF_TEMPORAL, UNRES_TEMPORAL
from Backend.Benchmark.shared.artifacts import create_run_directory


DEFAULT_SEEDS = (20260717, 20260718, 20260719, 20260720, 20260721)
DEFAULT_BLOCK_LENGTHS = (6, 12, 18, 24)
SEED_VARIANT_IDS = (
    "S3_X_t_HX",
    "S3_X_HX_T_RAW",
    "S3_X_HX_T_CONT",
    "S3_X_HX_T",
    "F11_X_t_HX_WX",
    "F11_X_HX_WX_T_RAW",
    "F11_X_HX_WX_T_CONT",
    "F11_X_HX_WX_T",
)
CONTROL_VARIANT_IDS = (*SEED_VARIANT_IDS, "N0_C", "NH_C_HC")
K_SWEEP_IDS = ("S0_M_t", "S1_X_t", "S3_X_t_HX", "S3_X_HX_T")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run reviewer-requested RQ1 controls and K sensitivity.")
    parser.add_argument("--snapshot-run-dir", type=Path, default=ROOT_DIR / "Backend/Benchmark/dataset_views/artifacts/dataset_views_20260729_164926_756176")
    parser.add_argument("--window-run-dir", type=Path, default=ROOT_DIR / "Backend/Benchmark/dataset_views/artifacts/dataset_views_20260729_164926_175188")
    parser.add_argument("--native-release-dir", type=Path, default=ROOT_DIR / "Backend/Benchmark/weak_labels/artifacts/phase_c/native_engine_20260805_045419_359073")
    parser.add_argument("--protocol-run-dir", type=Path, default=ROOT_DIR / "Backend/Benchmark/evaluation_protocols/artifacts/evaluation_protocols_20260902_203645")
    parser.add_argument("--target-view-run-dir", type=Path, default=ROOT_DIR / "Backend/Benchmark/weak_labels/artifacts/phase_c/temporal_event_online_target_views_20260903_000725")
    parser.add_argument("--output-root", type=Path, default=ROOT_DIR / "Backend/Benchmark/model_suite/artifacts")
    parser.add_argument("--seeds", nargs="+", type=int, default=list(DEFAULT_SEEDS))
    parser.add_argument("--block-lengths", nargs="+", type=int, default=list(DEFAULT_BLOCK_LENGTHS))
    parser.add_argument("--k-values", nargs="+", type=int, default=[2, 3, 4])
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--bootstrap-reps", type=int, default=1000)
    parser.add_argument("--seed-bootstrap-reps", type=int, default=300)
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
    history_bundle = build_causal_history_bundle(snapshot_frame=snapshot_frame, snapshot_feature_names=snapshot_names, window_frame=window_frame, window_feature_names=window_names, row_index=row_index, max_lags=12)
    base = build_representation_bundles(snapshot_bundle=snapshot_bundle, window_bundle=window_bundle, history_bundle=history_bundle)
    audit = build_history_audit_representations(representations=base, disruption_seed=args.seeds[0])
    nested = build_rq1_nested_representations(base_representations=base, audit_representations=audit)
    program = build_program_representations(snapshot_bundle=snapshot_bundle, window_bundle=window_bundle, history_bundle=history_bundle, nested=nested, row_index=row_index, window_audit=window_audit, negative_seed=args.seeds[0])
    target_frame, target_metadata = load_online_event_target_frame(native_release_dir=args.native_release_dir, protocol_run_dir=args.protocol_run_dir, target_view_run_dir=args.target_view_run_dir)
    target_frame = add_persistence_probe_target(target_frame)
    assignment_path = args.protocol_run_dir.resolve() / "temporal_diagnostics" / "support_5day" / "view_effective_split_assignments.parquet"
    fold_frames, _, fold_status = build_temporal_fold_frames(target_frame=target_frame, assignment_path=assignment_path, view_id="v2_temporal_3h", fold_ids=("fold_01", "fold_02", "fold_03"))
    run_id, output_dir = create_run_directory(args.output_root.resolve(), prefix="rq1_review_controls")

    control_representations = {key: program.representations[key] for key in CONTROL_VARIANT_IDS}
    seed_outputs: list[dict[str, pd.DataFrame]] = []
    first_seed_losses: pd.DataFrame | None = None
    for index, seed in enumerate(args.seeds):
        # Keep strict non-rule controls in every seed run.  These controls are
        # part of the reviewer-facing claim, so a single-seed result would not
        # satisfy the same-seed invariance requirement as the T decomposition.
        representation_ids = CONTROL_VARIANT_IDS
        variants = _build_variants({key: program.representations[key] for key in representation_ids}, seed)
        result = run_temporal_cv(
            variants=variants,
            fold_frames=fold_frames,
            output_dir=output_dir / "seed_runs" / f"seed_{seed}",
            random_seed=seed,
            thread_count=args.threads,
        )
        for key in result:
            if not result[key].empty:
                result[key].insert(0, "seed", seed)
        seed_outputs.append(result)
        if index == 0:
            aligned = add_temporal_order_columns(result["predictions"].drop(columns=["seed"]), row_index)
            first_seed_losses = build_per_anchor_losses(aligned)

    seed_metrics = _concat([result["metrics"] for result in seed_outputs])
    seed_summary = _summarize_seed_metrics(seed_metrics)
    seed_contrasts = _build_seed_contrasts(seed_outputs, row_index=row_index, args=args)
    if first_seed_losses is None:
        raise RuntimeError("The first reviewer-control seed produced no losses.")
    block_sensitivity = _build_block_sensitivity(first_seed_losses, args)

    k_metrics: list[pd.DataFrame] = []
    k_contrasts: list[pd.DataFrame] = []
    k_metadata: dict[str, object] = {}
    for k_value in args.k_values:
        k_frame = _derive_k_target_frame(target_frame, k_value)
        k_fold_frames, _, _ = build_temporal_fold_frames(target_frame=k_frame, assignment_path=assignment_path, view_id="v2_temporal_3h", fold_ids=("fold_01", "fold_02", "fold_03"))
        variants = _build_variants({key: program.representations[key] for key in K_SWEEP_IDS}, args.seeds[0], k=k_value)
        result = run_temporal_cv(
            variants=variants,
            fold_frames=k_fold_frames,
            output_dir=output_dir / "k_sweep" / f"k_{k_value}",
            random_seed=args.seeds[0],
            thread_count=args.threads,
        )
        metrics = result["metrics"].copy()
        metrics.insert(0, "k_value", k_value)
        k_metrics.append(metrics)
        aligned = add_temporal_order_columns(result["predictions"], row_index)
        losses = build_per_anchor_losses(aligned)
        _, contrasts = build_paired_contrasts(
            losses=losses,
            arrows=(
                ("S0_to_S1", "S0_M_t", "S1_X_t"),
                ("S1_to_S3", "S1_X_t", "S3_X_t_HX"),
                ("S3_to_S3T", "S3_X_t_HX", "S3_X_HX_T"),
            ),
            block_length=12,
            bootstrap_reps=args.seed_bootstrap_reps,
            seed=args.seeds[0] + k_value,
        )
        contrasts.insert(0, "k_value", k_value)
        k_contrasts.append(contrasts)
        k_metadata[str(k_value)] = _label_counts(k_frame, k_value)
    k_metrics_frame = _concat(k_metrics)
    k_summary = _summarize_k_metrics(k_metrics_frame)
    k_contrasts_frame = _concat(k_contrasts)

    gate_facts = _build_reporting_gate_facts(
        target_frame=target_frame,
        row_index=row_index,
        snapshot_names=snapshot_names,
        snapshot_manifest=snapshot_manifest,
        window_manifest=window_manifest,
        native_release_dir=args.native_release_dir,
        protocol_run_dir=args.protocol_run_dir,
    )
    manifest = {
        "run_id": run_id,
        "artifact_type": "RQ1_REVIEWER_CONTROLS",
        "artifact_status": "ANALYSIS_ONLY",
        "model_key": "xgboost",
        "seeds": list(args.seeds),
        "block_lengths": list(args.block_lengths),
        "k_values": list(args.k_values),
        "base_k_protocol": 3,
        "k_sweep_scope": "same_cohort_fixed_K3_protocol_assignments; labels re-derived from target lineage",
        "folds": ["fold_01", "fold_02", "fold_03"],
        "fold_status": fold_status,
        "target_metadata": target_metadata,
        "block_contract": program.block_contract,
        "review_controls": {
            "T_raw_timing": "lag-age fields and previous-row delta",
            "T_continuity": "prior counts/spans/gaps, boundaries, resets, actual window span",
            "N0_C": "eight current supporting sensors only; excludes moisture",
            "NH_C_HC": "eight current supporting sensors plus their 96 lags; excludes moisture and moisture lags",
            "seed_invariance": "five XGBoost training seeds for S3/F11 T decomposition and strict non-rule controls",
            "block_sensitivity": "L=6,12,18,24 on first-seed paired held-out losses",
        },
        "reporting_gate_facts": gate_facts,
        "k_label_counts": k_metadata,
        "source_paths": {"snapshot_run_dir": str(args.snapshot_run_dir.resolve()), "window_run_dir": str(args.window_run_dir.resolve()), "native_release_dir": str(args.native_release_dir.resolve()), "protocol_run_dir": str(args.protocol_run_dir.resolve()), "target_view_run_dir": str(args.target_view_run_dir.resolve()), "assignment_path": str(assignment_path), "output_dir": str(output_dir.resolve())},
        "source_manifest_hashes": {"snapshot": _manifest_hash(args.snapshot_run_dir.resolve() / "views" / "v0_minimal_sensor" / "manifest.json"), "window": _manifest_hash(args.window_run_dir.resolve() / "views" / "v2_sensor_row_window_3h" / "manifest.json")},
    }
    _write_outputs(output_dir, manifest, seed_metrics, seed_summary, seed_contrasts, block_sensitivity, k_metrics_frame, k_summary, k_contrasts_frame, gate_facts)
    print(json.dumps({"run_id": run_id, "output_dir": str(output_dir), "seed_count": len(args.seeds), "seed_metric_rows": len(seed_metrics), "k_metric_rows": len(k_metrics_frame), "block_rows": len(block_sensitivity)}, ensure_ascii=True))


def _build_variants(representations: dict[str, object], seed: int, k: int = 3) -> tuple[ConfiguredVariant, ...]:
    variants: list[ConfiguredVariant] = []
    for representation_id, representation in representations.items():
        for target_view_id, semantics, label_column in (("temporal_online_3h", f"K{k}_ONLINE_CAUSAL", "label_online"), ("temporal_event_3h", f"K{k}_EVENT_RETROSPECTIVE", "label_event")):
            variants.append(ConfiguredVariant(variant_id=f"review_seed{seed}_{target_view_id.removeprefix('temporal_')}_K{k}_{representation_id}", representation_id=representation_id, target_view_id=target_view_id, target_semantics=semantics, k=k, label_column=label_column, representation=representation))
    return tuple(variants)


def _derive_k_target_frame(target_frame: pd.DataFrame, k_value: int) -> pd.DataFrame:
    output = target_frame.copy()
    output["label_online"] = output.apply(lambda row: _online_label(row, k_value), axis=1).astype("string")
    output["label_event"] = output.apply(lambda row: _event_label(row, k_value), axis=1).astype("string")
    output["required_k"] = k_value
    return output.convert_dtypes()


def _online_label(row: pd.Series, k_value: int) -> object:
    point = str(row.get("source_label", ""))
    if point == LOW_POINT:
        return LOW_TEMPORAL if int(row.get("support_depth_at_anchor") or 0) >= k_value else UNRES_TEMPORAL
    if point == AUX_POINT:
        return UNRES_TEMPORAL
    if point == REF_POINT:
        return REF_TEMPORAL
    return pd.NA


def _event_label(row: pd.Series, k_value: int) -> object:
    point = str(row.get("source_label", ""))
    if point == LOW_POINT:
        if not bool(row.get("run_complete", False)):
            return pd.NA
        return LOW_TEMPORAL if int(row.get("eventual_run_length") or 0) >= k_value else UNRES_TEMPORAL
    if point == AUX_POINT:
        return UNRES_TEMPORAL
    if point == REF_POINT:
        return REF_TEMPORAL
    return pd.NA


def _build_seed_contrasts(seed_outputs: list[dict[str, pd.DataFrame]], *, row_index: pd.DataFrame, args: argparse.Namespace) -> pd.DataFrame:
    arrows = (
        ("S3_to_T_raw", "S3_X_t_HX", "S3_X_HX_T_RAW"),
        ("S3_to_T_cont", "S3_X_t_HX", "S3_X_HX_T_CONT"),
        ("S3_to_T_full", "S3_X_t_HX", "S3_X_HX_T"),
        ("F11_to_T_raw", "F11_X_t_HX_WX", "F11_X_HX_WX_T_RAW"),
        ("F11_to_T_cont", "F11_X_t_HX_WX", "F11_X_HX_WX_T_CONT"),
        ("F11_to_T_full", "F11_X_t_HX_WX", "F11_X_HX_WX_T"),
        ("N0_to_NH", "N0_C", "NH_C_HC"),
    )
    rows: list[pd.DataFrame] = []
    for result in seed_outputs:
        if result["predictions"].empty:
            continue
        seed = int(result["metrics"]["seed"].iloc[0])
        aligned = add_temporal_order_columns(result["predictions"].drop(columns=["seed"]), row_index)
        losses = build_per_anchor_losses(aligned)
        _, summary = build_paired_contrasts(losses=losses, arrows=arrows, block_length=12, bootstrap_reps=args.seed_bootstrap_reps, seed=seed)
        summary.insert(0, "seed", seed)
        rows.append(summary)
    return _concat(rows)


def _build_block_sensitivity(losses: pd.DataFrame, args: argparse.Namespace) -> pd.DataFrame:
    arrows = (
        ("S3_to_T_raw", "S3_X_t_HX", "S3_X_HX_T_RAW"),
        ("S3_to_T_cont", "S3_X_t_HX", "S3_X_HX_T_CONT"),
        ("S3_to_T_full", "S3_X_t_HX", "S3_X_HX_T"),
        ("F11_to_T_raw", "F11_X_t_HX_WX", "F11_X_HX_WX_T_RAW"),
        ("F11_to_T_cont", "F11_X_t_HX_WX", "F11_X_HX_WX_T_CONT"),
        ("F11_to_T_full", "F11_X_t_HX_WX", "F11_X_HX_WX_T"),
        ("N0_to_NH", "N0_C", "NH_C_HC"),
    )
    rows: list[pd.DataFrame] = []
    for block_length in args.block_lengths:
        _, summary = build_paired_contrasts(losses=losses, arrows=arrows, block_length=block_length, bootstrap_reps=args.bootstrap_reps, seed=args.seeds[0] + block_length)
        if "block_length" not in summary.columns:
            summary.insert(0, "block_length", block_length)
        rows.append(summary)
    return _concat(rows)


def _summarize_seed_metrics(metrics: pd.DataFrame) -> pd.DataFrame:
    if metrics.empty:
        return metrics
    return metrics.groupby(["seed", "variant_id", "target_view_id", "representation_id", "partition"], sort=True).agg(
        fold_count=("fold_id", "nunique"), evaluation_count_mean=("evaluation_count", "mean"), macro_f1_mean=("macro_f1", "mean"), macro_f1_std=("macro_f1", "std"), balanced_accuracy_mean=("balanced_accuracy", "mean"), macro_pr_auc_mean=("macro_pr_auc_ovr", "mean"), low_recall_mean=("low_recall", "mean"), unres_recall_mean=("unres_recall", "mean"), ref_recall_mean=("ref_recall", "mean"),
    ).reset_index().convert_dtypes()


def _summarize_k_metrics(metrics: pd.DataFrame) -> pd.DataFrame:
    if metrics.empty:
        return metrics
    return metrics.groupby(["k_value", "variant_id", "target_view_id", "representation_id", "partition"], sort=True).agg(
        fold_count=("fold_id", "nunique"), evaluation_count_mean=("evaluation_count", "mean"), macro_f1_mean=("macro_f1", "mean"), macro_f1_std=("macro_f1", "std"), balanced_accuracy_mean=("balanced_accuracy", "mean"), macro_pr_auc_mean=("macro_pr_auc_ovr", "mean"), low_recall_mean=("low_recall", "mean"), unres_recall_mean=("unres_recall", "mean"), ref_recall_mean=("ref_recall", "mean"),
    ).reset_index().convert_dtypes()


def _label_counts(frame: pd.DataFrame, k_value: int) -> dict[str, object]:
    trainable = frame["final_trainability"].fillna(False).astype(bool)
    return {"k": k_value, "online": frame.loc[trainable, "label_online"].value_counts().to_dict(), "event": frame.loc[trainable, "label_event"].value_counts().to_dict(), "online_labeled": int(frame.loc[trainable, "label_online"].notna().sum()), "event_labeled": int(frame.loc[trainable, "label_event"].notna().sum())}


def _build_reporting_gate_facts(*, target_frame: pd.DataFrame, row_index: pd.DataFrame, snapshot_names: list[str], snapshot_manifest: dict[str, object], window_manifest: dict[str, object], native_release_dir: Path, protocol_run_dir: Path) -> dict[str, object]:
    ids = set(target_frame["sample_id"].astype("string"))
    scoped = row_index.loc[row_index["record.id"].astype("string").isin(ids)].copy()
    timestamps = pd.to_datetime(scoped["record.ts_sample"], unit="s", utc=True)
    delta = scoped.sort_values(["record.node_id", "record.segment_id", "record.ts_sample", "source_row_position"]).groupby(["record.node_id", "record.segment_id"])["record.ts_sample"].diff().dropna()
    native_manifest_path = native_release_dir.resolve() / "run_metadata" / "run_manifest.json"
    native_manifest = json.loads(native_manifest_path.read_text(encoding="utf-8"))
    known = {
        "benchmark_authorized_record_count": native_manifest.get("input_metadata", {}).get("authorized_record_count"),
        "benchmark_time_start_utc": native_manifest.get("input_metadata", {}).get("environment_start_utc"),
        "benchmark_time_end_utc": native_manifest.get("input_metadata", {}).get("environment_end_utc"),
        "benchmark_environment_ids": [native_manifest.get("input_metadata", {}).get("environment_id")],
        "scoped_node_count": int(scoped["record.node_id"].nunique()),
        "scoped_nodes": sorted(scoped["record.node_id"].dropna().astype("string").unique().tolist()),
        "scoped_segment_count": int(scoped["record.segment_id"].nunique()),
        "scoped_sample_count": int(len(scoped)),
        "scoped_observation_start_utc": str(timestamps.min()),
        "scoped_observation_end_utc": str(timestamps.max()),
        "observed_median_delta_seconds": float(delta.median()) if not delta.empty else None,
        "observed_delta_p50_p95_seconds": [float(delta.quantile(0.5)), float(delta.quantile(0.95))] if not delta.empty else [],
        "snapshot_feature_count": len(snapshot_names),
        "snapshot_features": snapshot_names,
        "continuity_policy": window_manifest.get("continuity_policy", {}),
        "native_operationalization": native_manifest.get("operationalization_id"),
        "protocol_feature_view": "v2_temporal_full_3h",
        "source_manifest_hashes": {
            "snapshot_view": _manifest_hash(Path(snapshot_manifest.get("debug_csv_paths", {}).get("feature_matrix_csv", ""))) if False else snapshot_manifest.get("x_data_hash"),
            "window_view": window_manifest.get("x_data_hash"),
        },
    }
    pending = {
        "physical_hardware_log": "not found in repository; configuration files are not a substitute for a physical deployment log",
        "replay_buffer_server_upload_fields": "not available in the locked feature universe",
        "independent_agronomic_ground_truth": "not available in this benchmark",
        "K2_K4_frozen_protocol_release": "not available; K sweep is same-cohort sensitivity only",
    }
    return {"known": known, "pending": pending, "sources": [str(native_manifest_path), str(protocol_run_dir.resolve()), str(window_manifest.get("feature_artifact_path", ""))]}


def _write_outputs(output_dir: Path, manifest: dict[str, object], seed_metrics: pd.DataFrame, seed_summary: pd.DataFrame, seed_contrasts: pd.DataFrame, block_sensitivity: pd.DataFrame, k_metrics: pd.DataFrame, k_summary: pd.DataFrame, k_contrasts: pd.DataFrame, gate_facts: dict[str, object]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    seed_metrics.to_csv(output_dir / "seed_cv_metrics.csv", index=False)
    seed_summary.to_csv(output_dir / "seed_cv_summary.csv", index=False)
    seed_contrasts.to_csv(output_dir / "seed_invariance_contrasts.csv", index=False)
    block_sensitivity.to_csv(output_dir / "block_length_sensitivity.csv", index=False)
    k_metrics.to_csv(output_dir / "k_sweep_cv_metrics.csv", index=False)
    k_summary.to_csv(output_dir / "k_sweep_cv_summary.csv", index=False)
    k_contrasts.to_csv(output_dir / "k_sweep_contrasts.csv", index=False)
    (output_dir / "reporting_gate_facts.json").write_text(json.dumps(gate_facts, indent=2, ensure_ascii=True, default=str), encoding="utf-8")
    (output_dir / "run_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=True, default=str), encoding="utf-8")
    report = [
        "# RQ1 reviewer-requested controls",
        "",
        f"- run_id: `{manifest['run_id']}`",
        f"- seeds: `{manifest['seeds']}`",
        f"- block lengths: `{manifest['block_lengths']}`",
        f"- K values: `{manifest['k_values']}`",
        "",
        "## Scope",
        "",
        "T is decomposed into raw timing (lag-age and previous-row delta) and continuity (counts, spans, gaps, boundaries, resets, and actual window span). N0=C and NH=C+H_C exclude moisture and moisture lags.",
        "K=2/4 use the same K3 protocol fold assignments and are therefore sensitivity results, not new frozen protocol releases.",
        "",
        "## Seed invariance — paired log-loss contrasts",
        "",
        _markdown_table(seed_contrasts, ["seed", "arrow", "target_view_id", "delta_log_loss_mean_across_folds", "pooled_delta_log_loss_ci_low", "pooled_delta_log_loss_ci_high"]),
        "",
        "## Block-length sensitivity",
        "",
        _markdown_table(block_sensitivity, ["block_length", "arrow", "target_view_id", "pooled_delta_log_loss", "pooled_delta_log_loss_ci_low", "pooled_delta_log_loss_ci_high"]),
        "",
        "## K sensitivity",
        "",
        _markdown_table(k_contrasts, ["k_value", "arrow", "target_view_id", "delta_log_loss_mean_across_folds", "pooled_delta_log_loss_ci_low", "pooled_delta_log_loss_ci_high"]),
        "",
        "## Reporting gate",
        "",
        "Known manifest/data facts:",
        "",
    ]
    for key, value in gate_facts.get("known", {}).items():
        report.append(f"- `{key}`: `{value}`")
    report.extend(["", "Pending facts:", ""])
    for key, value in gate_facts.get("pending", {}).items():
        report.append(f"- `{key}`: {value}")
    (output_dir / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")


def _summarize_seed_metrics(metrics: pd.DataFrame) -> pd.DataFrame:
    return _group_summary(metrics, "seed")


def _group_summary(metrics: pd.DataFrame, group_column: str) -> pd.DataFrame:
    if metrics.empty:
        return metrics
    return metrics.groupby([group_column, "variant_id", "target_view_id", "representation_id", "partition"], sort=True).agg(
        fold_count=("fold_id", "nunique"), evaluation_count_mean=("evaluation_count", "mean"), macro_f1_mean=("macro_f1", "mean"), macro_f1_std=("macro_f1", "std"), balanced_accuracy_mean=("balanced_accuracy", "mean"), macro_pr_auc_mean=("macro_pr_auc_ovr", "mean"), low_recall_mean=("low_recall", "mean"), unres_recall_mean=("unres_recall", "mean"), ref_recall_mean=("ref_recall", "mean"),
    ).reset_index().convert_dtypes()


def _summarize_k_metrics(metrics: pd.DataFrame) -> pd.DataFrame:
    return _group_summary(metrics, "k_value")


def _concat(frames: list[pd.DataFrame]) -> pd.DataFrame:
    nonempty = [frame for frame in frames if not frame.empty]
    return pd.concat(nonempty, ignore_index=True).convert_dtypes() if nonempty else pd.DataFrame()


def _manifest_hash(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _markdown_table(frame: pd.DataFrame, columns: list[str]) -> str:
    if frame.empty:
        return "_empty_"
    selected = [column for column in columns if column in frame.columns]
    view = frame.loc[:, selected].copy()
    for column in view.columns:
        if pd.api.types.is_numeric_dtype(view[column]):
            view[column] = view[column].map(lambda value: "" if pd.isna(value) else f"{float(value):.4f}")
        else:
            view[column] = view[column].astype("string").fillna("")
    headers = [str(value) for value in view.columns]
    rows = [[str(value) for value in row] for row in view.itertuples(index=False, name=None)]
    all_rows = [headers, *rows]
    widths = [max(len(row[index]) for row in all_rows) for index in range(len(headers))]
    fmt = lambda row: "| " + " | ".join(value.ljust(widths[index]) for index, value in enumerate(row)) + " |"
    return "\n".join([fmt(headers), "| " + " | ".join("-" * width for width in widths) + " |", *[fmt(row) for row in rows]])


if __name__ == "__main__":
    main()
