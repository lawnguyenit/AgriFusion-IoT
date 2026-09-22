from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[5]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from Backend.Benchmark.model_suite.analysis.k_window_variants.reporting import write_analysis_outputs
from Backend.Benchmark.model_suite.analysis.k_window_variants.runner import build_variant_definitions, run_variants
from Backend.Benchmark.model_suite.analysis.k_window_variants.targets import load_temporal_target_frame
from Backend.Benchmark.shared.artifacts import create_run_directory


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the four-way full-9/3h-window x K benchmark.")
    parser.add_argument("--snapshot-run-dir", type=Path, default=ROOT_DIR / "Backend/Benchmark/dataset_views/artifacts/dataset_views_20260729_164926_756176")
    parser.add_argument("--window-run-dir", type=Path, default=ROOT_DIR / "Backend/Benchmark/dataset_views/artifacts/dataset_views_20260729_164926_175188")
    parser.add_argument("--native-release-dir", type=Path, default=ROOT_DIR / "Backend/Benchmark/weak_labels/artifacts/phase_c/native_engine_20260805_045419_359073")
    parser.add_argument("--protocol-run-dir", type=Path, default=ROOT_DIR / "Backend/Benchmark/evaluation_protocols/artifacts/evaluation_protocols_20260902_203645")
    parser.add_argument("--output-root", type=Path, default=ROOT_DIR / "Backend/Benchmark/model_suite/artifacts")
    parser.add_argument("--seed", type=int, default=20260717)
    parser.add_argument("--threads", type=int, default=1)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    target_frame, target_metadata = load_temporal_target_frame(
        native_release_dir=args.native_release_dir,
        protocol_run_dir=args.protocol_run_dir,
    )
    variants = build_variant_definitions(
        snapshot_run_dir=args.snapshot_run_dir,
        window_run_dir=args.window_run_dir,
    )
    run_id, output_dir = create_run_directory(args.output_root.resolve(), prefix="k_window_variants")
    metrics, per_class, confusion, predictions = run_variants(
        variants=variants,
        target_frame=target_frame,
        output_dir=output_dir,
        random_seed=args.seed,
        thread_count=args.threads,
    )
    run_manifest = {
        "run_id": run_id,
        "artifact_type": "FOUR_WAY_K_WINDOW_BENCHMARK",
        "artifact_status": "ANALYSIS_ONLY",
        "model_key": "xgboost",
        "random_seed": args.seed,
        "thread_count": args.threads,
        "fold_policy": "E1_PRIMARY_7D_V1 / fold_01",
        "target_semantics": "Q10 temporal-3h persistence labels; K=1 and K=3",
        "k3_native_release_preserved": True,
        "k1_analysis_derived": True,
        "target_metadata": target_metadata,
        "source_paths": {
            "snapshot_run_dir": str(args.snapshot_run_dir.resolve()),
            "window_run_dir": str(args.window_run_dir.resolve()),
            "native_release_dir": str(args.native_release_dir.resolve()),
            "protocol_run_dir": str(args.protocol_run_dir.resolve()),
        },
        "source_manifest_hashes": _source_manifest_hashes(variants),
    }
    write_analysis_outputs(
        output_dir=output_dir,
        run_manifest=run_manifest,
        target_frame=target_frame,
        variants=variants,
        metrics=metrics,
        per_class=per_class,
        confusion=confusion,
        predictions=predictions,
    )
    print(json.dumps({"run_id": run_id, "output_dir": str(output_dir), "metrics_rows": len(metrics)}, ensure_ascii=True))


def _source_manifest_hashes(variants) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for variant in variants:
        path = variant.feature_run_dir.resolve() / "views" / variant.feature_view_id / "manifest.json"
        hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


if __name__ == "__main__":
    main()
