from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[5]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from Backend.Benchmark.shared.artifacts import create_run_directory

from .reporting import build_report_tables, render_markdown
from .representations import build_representations
from .runner import run_world_calibration
from .worlds import WORLD_IDS, generate_world


DEFAULT_SEEDS = (20260923, 20260924, 20260925)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run WADE controlled-world calibration.")
    parser.add_argument("--worlds", nargs="+", choices=WORLD_IDS, default=list(WORLD_IDS))
    parser.add_argument("--n-samples", type=int, default=8_000)
    parser.add_argument("--seeds", nargs="+", type=int, default=list(DEFAULT_SEEDS))
    parser.add_argument("--bootstrap-reps", type=int, default=500)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--output-root", type=Path, default=ROOT_DIR / "Backend/Benchmark/model_suite/artifacts")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run_id, output_dir = create_run_directory(args.output_root.resolve(), prefix="wade_controlled_worlds")
    all_metrics: list[pd.DataFrame] = []
    all_losses: list[pd.DataFrame] = []
    all_oracle: list[pd.DataFrame] = []
    contracts: dict[str, object] = {}
    metadata: dict[str, object] = {}
    for index, world_id in enumerate(args.worlds):
        data_seed = 1_000_003 + index * 7_919
        dataset = generate_world(world_id=world_id, n_samples=args.n_samples, data_seed=data_seed)
        world_dir = output_dir / "worlds" / world_id
        world_dir.mkdir(parents=True, exist_ok=True)
        dataset.frame.to_csv(world_dir / "dataset.csv", index=False)
        (world_dir / "metadata.json").write_text(json.dumps(dataset.metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        representations = build_representations(dataset=dataset, disruption_seed=data_seed + 101)
        contracts[world_id] = {
            representation_id: {
                "feature_count": len(representation.feature_names),
                "feature_names": list(representation.feature_names),
                "feature_groups": representation.feature_groups,
                "description": representation.description,
            }
            for representation_id, representation in representations.items()
        }
        metadata[world_id] = dataset.metadata
        metrics, losses, oracle = run_world_calibration(
            dataset=dataset,
            representations=representations,
            seeds=tuple(args.seeds),
            output_dir=output_dir,
            thread_count=args.threads,
        )
        all_metrics.append(metrics)
        all_losses.append(losses)
        all_oracle.append(oracle)

    metrics = pd.concat(all_metrics, ignore_index=True).convert_dtypes()
    losses = pd.concat(all_losses, ignore_index=True).convert_dtypes()
    oracle = pd.concat(all_oracle, ignore_index=True).convert_dtypes()
    report = build_report_tables(
        metrics=metrics,
        losses=losses,
        oracle_metrics=oracle,
        bootstrap_reps=args.bootstrap_reps,
        seed=args.seeds[0],
    )
    metrics.to_csv(output_dir / "seed_metrics.csv", index=False)
    report.metric_summary.to_csv(output_dir / "metric_summary.csv", index=False)
    losses.to_csv(output_dir / "test_anchor_losses.csv", index=False)
    report.paired_contrasts.to_csv(output_dir / "paired_contrasts.csv", index=False)
    report.contrast_summary.to_csv(output_dir / "contrast_summary.csv", index=False)
    oracle.to_csv(output_dir / "oracle_metrics.csv", index=False)
    report.gates.to_csv(output_dir / "calibration_gates.csv", index=False)
    (output_dir / "representation_contract.json").write_text(json.dumps(contracts, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    manifest = {
        "run_id": run_id,
        "artifact_type": "WADE_CONTROLLED_WORLD_CALIBRATION",
        "artifact_status": "ANALYSIS_ONLY",
        "world_ids": list(args.worlds),
        "n_samples": args.n_samples,
        "seeds": list(args.seeds),
        "bootstrap_repetitions": args.bootstrap_reps,
        "thread_count": args.threads,
        "model_key": "xgboost",
        "dataset_metadata": metadata,
        "representation_contract_path": str((output_dir / "representation_contract.json").resolve()),
        "calibration_status": "PASS" if bool(report.gates["passed"].all()) else "FAIL",
        "gate_count": int(len(report.gates)),
        "passed_gate_count": int(report.gates["passed"].sum()),
    }
    (output_dir / "run_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (output_dir / "report.md").write_text(render_markdown(report=report, manifest=manifest), encoding="utf-8")
    print(json.dumps({"run_id": run_id, "output_dir": str(output_dir), "calibration_status": manifest["calibration_status"], "gate_count": manifest["gate_count"], "passed_gate_count": manifest["passed_gate_count"], "metric_rows": len(metrics), "loss_rows": len(losses)}, ensure_ascii=True))


if __name__ == "__main__":
    main()
