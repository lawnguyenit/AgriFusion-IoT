from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


PAIR_DEFINITIONS = (
    ("S1_to_S3", "S1_snapshot", "S3_history"),
    ("S3_disrupted_to_S3", "S3_history_disrupted", "S3_history"),
    ("R_reduced_to_R_full", "R_reduced", "R_full"),
    ("S1_to_S1_plus_A", "S1_snapshot", "S1_plus_A"),
    ("A_disrupted_to_A", "A_disrupted_only", "A_only"),
)


@dataclass(frozen=True)
class CalibrationReport:
    seed_metrics: pd.DataFrame
    metric_summary: pd.DataFrame
    paired_contrasts: pd.DataFrame
    contrast_summary: pd.DataFrame
    oracle_metrics: pd.DataFrame
    gates: pd.DataFrame


def build_report_tables(*, metrics: pd.DataFrame, losses: pd.DataFrame, oracle_metrics: pd.DataFrame, bootstrap_reps: int, seed: int) -> CalibrationReport:
    paired = build_paired_contrasts(losses=losses, bootstrap_reps=bootstrap_reps, seed=seed)
    metric_summary = (
        metrics.groupby(["world_id", "representation_id", "partition"], sort=True)
        .agg(
            seed_count=("seed", "nunique"),
            evaluation_count_mean=("evaluation_count", "mean"),
            log_loss_mean=("log_loss", "mean"),
            log_loss_sd=("log_loss", "std"),
            brier_loss_mean=("brier_loss", "mean"),
            macro_f1_mean=("macro_f1", "mean"),
            macro_f1_sd=("macro_f1", "std"),
            balanced_accuracy_mean=("balanced_accuracy", "mean"),
        )
        .reset_index()
        .convert_dtypes()
    )
    contrast_summary = (
        paired.groupby(["world_id", "arrow"], sort=True)
        .agg(
            seed_count=("seed", "nunique"),
            delta_log_loss_mean=("delta_log_loss", "mean"),
            delta_log_loss_sd=("delta_log_loss", "std"),
            ci_low_mean=("ci_low", "mean"),
            ci_high_mean=("ci_high", "mean"),
        )
        .reset_index()
        .convert_dtypes()
    )
    world_ids = tuple(sorted(metrics["world_id"].astype("string").unique().tolist()))
    gates = evaluate_calibration_gates(world_ids=world_ids, metric_summary=metric_summary, contrast_summary=contrast_summary, oracle_metrics=oracle_metrics)
    return CalibrationReport(
        seed_metrics=metrics,
        metric_summary=metric_summary,
        paired_contrasts=paired,
        contrast_summary=contrast_summary,
        oracle_metrics=oracle_metrics,
        gates=gates,
    )


def build_paired_contrasts(*, losses: pd.DataFrame, bootstrap_reps: int, seed: int) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for world_id in sorted(losses["world_id"].astype("string").unique()):
        world = losses.loc[losses["world_id"].astype("string").eq(world_id)]
        for arrow, previous, following in PAIR_DEFINITIONS:
            left = world.loc[world["representation_id"].astype("string").eq(previous), ["seed", "sample_id", "sequence_id", "log_loss"]]
            right = world.loc[world["representation_id"].astype("string").eq(following), ["seed", "sample_id", "sequence_id", "log_loss"]]
            joined = left.merge(right, on=["seed", "sample_id", "sequence_id"], suffixes=("_previous", "_following"), validate="one_to_one")
            if joined.empty:
                continue
            joined["delta_log_loss"] = joined["log_loss_previous"] - joined["log_loss_following"]
            for run_seed, subset in joined.groupby("seed", sort=True):
                bootstrap = _sequence_bootstrap(subset, repetitions=bootstrap_reps, seed=seed + int(run_seed) + len(arrow))
                rows.append(
                    {
                        "world_id": str(world_id),
                        "arrow": arrow,
                        "previous_representation_id": previous,
                        "next_representation_id": following,
                        "seed": int(run_seed),
                        "anchor_count": int(len(subset)),
                        "delta_log_loss": float(subset["delta_log_loss"].mean()),
                        "ci_low": float(np.percentile(bootstrap, 2.5)),
                        "ci_high": float(np.percentile(bootstrap, 97.5)),
                    }
                )
    return pd.DataFrame(rows).convert_dtypes()


def evaluate_calibration_gates(*, world_ids: tuple[str, ...], metric_summary: pd.DataFrame, contrast_summary: pd.DataFrame, oracle_metrics: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for world_id in world_ids:
        rows.extend(_world_gates(world_id=world_id, metric_summary=metric_summary, contrast_summary=contrast_summary, oracle_metrics=oracle_metrics))
    return pd.DataFrame(rows).convert_dtypes()


def render_markdown(*, report: CalibrationReport, manifest: dict[str, object]) -> str:
    lines = [
        "# WADE controlled-world calibration",
        "",
        f"- run_id: `{manifest['run_id']}`",
        f"- worlds: `{manifest['world_ids']}`",
        f"- rows per world: `{manifest['n_samples']}`",
        f"- seeds: `{manifest['seeds']}`",
        "",
        "## Interpretation rule",
        "",
        "Positive paired delta-log-loss means the following representation has lower held-out loss. A calibration pass means the predefined mechanism signature is observed; it is not a claim of external validity.",
        "",
        "## Calibration gates",
        "",
        _markdown_table(report.gates, ["world_id", "gate", "observed", "threshold", "passed", "interpretation"]),
        "",
        "## Paired contrasts",
        "",
        _markdown_table(report.contrast_summary, ["world_id", "arrow", "delta_log_loss_mean", "delta_log_loss_sd", "ci_low_mean", "ci_high_mean"]),
        "",
        "## Test metrics",
        "",
        _markdown_table(report.metric_summary.loc[report.metric_summary["partition"].astype("string").eq("test")], ["world_id", "representation_id", "seed_count", "log_loss_mean", "brier_loss_mean", "macro_f1_mean", "macro_f1_sd", "balanced_accuracy_mean"]),
        "",
        "## Oracle control",
        "",
        _markdown_table(report.oracle_metrics, ["world_id", "partition", "oracle_accuracy", "oracle_macro_f1", "oracle_disagreement_rate"]),
        "",
        "## Scope and limits",
        "",
        "- W_S--W_A are synthetic mechanism-calibration worlds, not field observations.",
        "- The oracle is a positive control generated from the known mechanism and is not an independently observed label source.",
        "- A passed calibration supports WADE mechanism identification under controlled construction; it does not establish cross-domain validity.",
    ]
    return "\n".join(lines) + "\n"


def _world_gates(*, world_id: str, metric_summary: pd.DataFrame, contrast_summary: pd.DataFrame, oracle_metrics: pd.DataFrame) -> list[dict[str, object]]:
    def delta(arrow: str) -> float:
        row = contrast_summary.loc[(contrast_summary["world_id"] == world_id) & (contrast_summary["arrow"] == arrow)]
        return float(row["delta_log_loss_mean"].iloc[0]) if not row.empty else float("nan")

    def f1(rep: str) -> float:
        row = metric_summary.loc[(metric_summary["world_id"] == world_id) & (metric_summary["representation_id"] == rep) & (metric_summary["partition"] == "test")]
        return float(row["macro_f1_mean"].iloc[0]) if not row.empty else float("nan")

    def add(gate: str, observed: float, threshold: str, passed: bool, interpretation: str) -> dict[str, object]:
        return {"world_id": world_id, "gate": gate, "observed": observed, "threshold": threshold, "passed": bool(passed), "interpretation": interpretation}

    if world_id == "W_S":
        value = delta("S1_to_S3")
        return [add("snapshot_sufficiency", value, "delta <= 0.03", bool(value <= 0.03), "history adds little incremental information")]
    if world_id == "W_H":
        history_gain = delta("S1_to_S3")
        disruption_gain = delta("S3_disrupted_to_S3")
        return [
            add("history_required", history_gain, "delta >= 0.05", bool(history_gain >= 0.05), "history improves over snapshot"),
            add("history_disruption", disruption_gain, "delta >= 0.03", bool(disruption_gain >= 0.03), "permuting history removes useful structure"),
        ]
    if world_id == "W_R":
        rule_f1 = f1("R_full")
        oracle = oracle_metrics.loc[(oracle_metrics["world_id"] == world_id) & (oracle_metrics["partition"] == "test")]
        disagreement = float(oracle["oracle_disagreement_rate"].iloc[0]) if not oracle.empty else float("nan")
        timing_gain = delta("R_reduced_to_R_full")
        return [
            add("rule_full_recoverability", rule_f1, "Macro-F1 >= 0.95", bool(rule_f1 >= 0.95), "full rule operands reconstruct the deterministic target"),
            add("oracle_consistency", disagreement, "disagreement <= 0.00", bool(disagreement <= 0.0), "oracle reproduces its own generated target"),
            add("timing_operand_sensitivity", timing_gain, "delta > 0", bool(timing_gain > 0.0), "removing timing operands changes the rule reconstruction task"),
        ]
    acquisition_gain = delta("S1_to_S1_plus_A")
    acquisition_only = f1("A_only")
    broken_gain = delta("A_disrupted_to_A")
    return [
        add("acquisition_addition", acquisition_gain, "delta >= 0.05", bool(acquisition_gain >= 0.05), "adding acquisition pattern improves prediction"),
        add("acquisition_only_signal", acquisition_only, "Macro-F1 >= 0.50", bool(acquisition_only >= 0.50), "acquisition-only model is predictively above the balanced three-class floor"),
        add("acquisition_disruption", broken_gain, "delta >= 0.05", bool(broken_gain >= 0.05), "breaking acquisition alignment removes the shortcut"),
    ]


def _sequence_bootstrap(frame: pd.DataFrame, *, repetitions: int, seed: int) -> np.ndarray:
    grouped = frame.groupby("sequence_id", sort=True)["delta_log_loss"].mean().to_numpy(dtype=float)
    if len(grouped) == 0:
        return np.array([np.nan])
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(grouped), size=(repetitions, len(grouped)))
    return grouped[indices].mean(axis=1)


def _markdown_table(frame: pd.DataFrame, columns: list[str]) -> str:
    if frame.empty:
        return "_empty_"
    view = frame.loc[:, [column for column in columns if column in frame.columns]].copy()
    for column in view.columns:
        if pd.api.types.is_numeric_dtype(view[column]):
            view[column] = view[column].map(lambda value: "" if pd.isna(value) else f"{float(value):.4f}")
        else:
            view[column] = view[column].astype("string").fillna("")
    rows = [[str(value) for value in row] for row in view.itertuples(index=False, name=None)]
    headers = [str(column) for column in view.columns]
    all_rows = [headers, *rows]
    widths = [max(len(row[index]) for row in all_rows) for index in range(len(headers))]
    fmt = lambda row: "| " + " | ".join(value.ljust(widths[index]) for index, value in enumerate(row)) + " |"
    return "\n".join([fmt(headers), "| " + " | ".join("-" * width for width in widths) + " |", *[fmt(row) for row in rows]])
