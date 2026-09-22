from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .layer1_geometry import build_layer1_tables
from .layer2_probe import run_layer2_probe


DEFAULT_OUTPUT = Path("Docs/Temp/temporal_weak_target_probe_20260907")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the temporary weak-target robustness probe.")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--seed", type=int, default=20260907)
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    output_dir = args.output_dir if args.output_dir.is_absolute() else repo_root / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    layer1_tables, layer1_summary = build_layer1_tables(repo_root)
    for name, table in layer1_tables.items():
        table.to_csv(output_dir / f"layer1_{name}.csv", index=False)

    layer2 = run_layer2_probe(repo_root, seed=args.seed)
    layer2["metrics"].to_csv(output_dir / "layer2_metrics.csv", index=False)
    layer2["disruption_audit"].to_csv(output_dir / "layer2_disruption_audit.csv", index=False)
    layer2["arm_metadata"].to_csv(output_dir / "layer2_arm_metadata.csv", index=False)

    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "repo_root": str(repo_root),
        "output_dir": str(output_dir),
        "layer1": layer1_summary,
        "layer2": layer2["contract"],
        "source_artifacts": {
            "phase_b_candidate_pack": "Backend/Benchmark/weak_labels/artifacts/phase_b/phase_b_decision_pack_20260805_091658",
            "phase_c_unres_origin": "Backend/Benchmark/weak_labels/artifacts/phase_c/temporal_unres_origin_split_20260902_213111",
            "temporal_protocol": "Backend/Benchmark/evaluation_protocols/artifacts/evaluation_protocols_20260902_203645",
        },
    }
    (output_dir / "probe_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8"
    )
    (output_dir / "probe_report.md").write_text(
        _render_report(layer1_tables, layer1_summary, layer2["metrics"], layer2["contract"], output_dir),
        encoding="utf-8",
    )
    print(json.dumps({"output_dir": str(output_dir), "layer1": layer1_summary, "layer2_metrics": layer2["metrics"].to_dict("records")}, ensure_ascii=False, indent=2, default=_json_default))


def _render_report(
    layer1_tables: dict[str, pd.DataFrame],
    layer1_summary: dict[str, object],
    metrics: pd.DataFrame,
    contract: dict[str, object],
    output_dir: Path,
) -> str:
    test = metrics.loc[metrics["partition"].eq("test")].copy()
    lines = [
        "# Temporary temporal weak-target robustness probe",
        "",
        "> Diagnostic artifact only. Candidate labels remain rule-generated and candidate-only.",
        "",
        "## 1. Layer 1 — target geometry",
        "",
        f"- Geometry changed enough to continue to the partial Layer 2 probe: **{layer1_summary['geometry_changed_enough_for_layer2']}**.",
        f"- Point prevalence: `{json.dumps(layer1_summary['point_prevalence'], ensure_ascii=False)}`.",
        f"- Q10 event survival from K1: `{json.dumps(layer1_summary['q10_event_survival_from_k1'], ensure_ascii=False)}`.",
        f"- Material boundary shift observed: **{layer1_summary['boundary_material_shift_observed']}**.",
        f"- Q10-K3 unresolved origin: `{json.dumps(layer1_summary['unresolved_origin_counts'], ensure_ascii=False)}`.",
        "",
        "The detailed tables are in `layer1_*.csv`. The strongest current signal is target geometry changing with Q/K; boundary movement is small in this data.",
        "",
        "## 2. Layer 2 partial — one matched XGBoost probe",
        "",
        "The probe keeps the Q10-K3 temporal target, fold and seed fixed. It compares five base sensor values, the existing 3h causal history features, and a deterministic disrupted-history control. It does not run hyperparameter search and does not persist model weights.",
        "",
        "| Arm | Partition | Rows | Features | Accuracy | Balanced accuracy | Macro-F1 | Macro recall |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in test.itertuples(index=False):
        lines.append(
            f"| {row.arm} | {row.partition} | {row.row_count} | {row.feature_count} | {row.accuracy:.4f} | {row.balanced_accuracy:.4f} | {row.macro_f1:.4f} | {row.macro_recall:.4f} |"
        )
    lines.extend(
        [
            "",
            "## 3. Interpretation boundary",
            "",
            "- This is enough to test whether a temporal intervention is worth examining further; it is not enough to claim a stable phenomenon.",
            "- A history gain over snapshot is only interesting if it is materially larger than the disrupted-history result and survives repeats.",
            "- A disrupted-history result close to causal history would indicate that added dimensions/statistics may explain the gain; it would not support a temporal-order claim.",
            "- The next decision should be made from the CSV/JSON artifacts, not from this one-fold score alone.",
            "",
            f"Output directory: `{output_dir}`.",
        ]
    )
    return "\n".join(lines) + "\n"


def _json_default(value: object) -> object:
    if hasattr(value, "item"):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Unsupported JSON value: {type(value)!r}")


if __name__ == "__main__":
    main()
