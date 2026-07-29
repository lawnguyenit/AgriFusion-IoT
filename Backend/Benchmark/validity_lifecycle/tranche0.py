from __future__ import annotations

import math
from pathlib import Path

import pandas as pd
import yaml

from Backend.Benchmark.model_suite.registries.model_catalog import DEFAULT_ARTIFACT_ROOT as MODEL_SUITE_ARTIFACT_ROOT


LEGACY_COMPARISON_ALIASES: dict[str, str] = {
    "v0_vs_v2_mini_3h": "CMP_HISTORY_MINI_3H",
    "v1_vs_v2_full_3h": "CMP_HISTORY_FULL_3H",
    "v0_vs_v2_mini_8h": "CMP_HISTORY_MINI_8H",
    "v1_vs_v2_full_8h": "CMP_HISTORY_FULL_8H",
}


def resolve_latest_model_suite_run() -> Path:
    candidates = [path for path in MODEL_SUITE_ARTIFACT_ROOT.iterdir() if path.is_dir()] if MODEL_SUITE_ARTIFACT_ROOT.exists() else []
    if not candidates:
        raise FileNotFoundError("No model_suite artifact runs were found.")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def load_claim_and_comparison_inputs(protocol_run_dir: Path) -> tuple[dict[str, object], pd.DataFrame, pd.DataFrame]:
    run_metadata = protocol_run_dir / "run_metadata"
    with (run_metadata / "claim_registry.yaml").open("r", encoding="utf-8") as handle:
        claim_registry = yaml.safe_load(handle)
    comparison_registry = pd.read_csv(run_metadata / "comparison_registry.csv").convert_dtypes()
    experiment_registry = pd.read_csv(run_metadata / "experiment_registry.csv").convert_dtypes()
    return claim_registry, comparison_registry, experiment_registry


def load_model_suite_outputs(model_suite_run_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    smoke_dir = model_suite_run_dir / "smoke_protocol"
    if smoke_dir.exists():
        predictions = pd.read_csv(smoke_dir / "per_sample_predictions.csv").convert_dtypes()
        pooled_metrics = pd.read_csv(smoke_dir / "pooled_metrics.csv").convert_dtypes()
        summary = pd.read_csv(smoke_dir / "smoke_model_summary.csv").convert_dtypes()
        return predictions, pooled_metrics, summary
    profiles_root = model_suite_run_dir / "profiles"
    profile_dirs = [path for path in profiles_root.iterdir() if path.is_dir()] if profiles_root.exists() else []
    if not profile_dirs:
        raise FileNotFoundError(f"No model_suite output profile could be resolved under {model_suite_run_dir}.")
    latest_profile = max(profile_dirs, key=lambda path: path.stat().st_mtime)
    predictions = pd.read_csv(latest_profile / "per_sample_predictions.csv").convert_dtypes()
    pooled_metrics = pd.read_csv(latest_profile / "pooled_metrics.csv").convert_dtypes()
    summary = pd.read_csv(latest_profile / "training_summary.csv").convert_dtypes()
    return predictions, pooled_metrics, summary


def build_tranche0_synthesis(
    *,
    claim_registry: dict[str, object],
    comparison_registry: pd.DataFrame,
    experiment_registry: pd.DataFrame,
    predictions_df: pd.DataFrame,
    pooled_metrics_df: pd.DataFrame,
) -> dict[str, object]:
    comparison_rows = comparison_registry.copy()
    comparison_rows["legacy_comparison_id"] = comparison_rows["comparison_id"].map(
        {value: key for key, value in LEGACY_COMPARISON_ALIASES.items()}
    ).astype("string")
    primary_model_lookup = {
        str(claim["claim_id"]): str(claim.get("primary_model_profile", "logistic_regression"))
        for claim in claim_registry.get("claims", [])
    }
    dependency_rows: list[dict[str, object]] = []
    stability_rows: list[dict[str, object]] = []
    classification_rows: list[dict[str, object]] = []
    uncertainty_rows: list[dict[str, object]] = []
    evidence_rows: list[dict[str, object]] = []

    for comparison in comparison_rows.to_dict(orient="records"):
        comparison_id = str(comparison["comparison_id"])
        legacy_alias = str(comparison.get("legacy_comparison_id", ""))
        claim_id = str(comparison["claim_id"])
        primary_model_key = primary_model_lookup.get(claim_id, "logistic_regression")
        metric_rows = pooled_metrics_df.loc[
            pooled_metrics_df["model_key"].astype("string").eq(primary_model_key)
            & pooled_metrics_df["run_scope"].astype("string").eq("comparison")
            & pooled_metrics_df["comparison_id"].astype("string").eq(legacy_alias)
            & pooled_metrics_df["partition"].astype("string").eq("test")
        ].copy()
        by_side = {
            str(side): side_frame.iloc[0]
            for side, side_frame in metric_rows.groupby("comparison_side", dropna=False, sort=False)
        }
        baseline_row = by_side.get("left")
        treatment_row = by_side.get("right")
        estimability_status = "NONE"
        effect_value = math.nan
        environment_id = "UNRESOLVED"
        metric_id = str(comparison.get("primary_metric_id", "supported_class_macro_f1"))
        interpretation_limit = str(comparison.get("interpretation_limit", "registered comparison only"))
        if baseline_row is not None and treatment_row is not None:
            baseline_metric = _resolve_effect_metric(baseline_row)
            treatment_metric = _resolve_effect_metric(treatment_row)
            if pd.notna(baseline_metric) and pd.notna(treatment_metric):
                estimability_status = "FULL"
                effect_value = float(treatment_metric - baseline_metric)
            else:
                estimability_status = "PARTIAL"
            treatment_predictions = predictions_df.loc[
                predictions_df["comparison_id"].astype("string").eq(legacy_alias)
                & predictions_df["comparison_side"].astype("string").eq("right")
            ].copy()
            if not treatment_predictions.empty and "environment_id" in treatment_predictions.columns:
                environment_ids = treatment_predictions["environment_id"].astype("string").dropna().unique().tolist()
                environment_id = environment_ids[0] if len(environment_ids) == 1 else ",".join(sorted(environment_ids))
        dependency_status = _classify_dependency(effect_value=effect_value, estimability_status=estimability_status)
        dependency_rows.append(
            {
                "comparison_id": comparison_id,
                "legacy_comparison_id": legacy_alias if legacy_alias else pd.NA,
                "claim_id": claim_id,
                "estimand_id": comparison.get("estimand_id", pd.NA),
                "environment_id": environment_id,
                "model_key": primary_model_key,
                "effect_metric_id": metric_id,
                "effect_value": effect_value,
                "estimability_status": estimability_status,
                "interpretation_limit": interpretation_limit,
            }
        )
        stability_rows.append(
            {
                "claim_id": claim_id,
                "comparison_id": comparison_id,
                "environment_id": environment_id,
                "effect_value": effect_value,
                "estimability_status": estimability_status,
            }
        )
        classification_rows.append(
            {
                "claim_id": claim_id,
                "comparison_id": comparison_id,
                "estimability_status": estimability_status,
                "dependency_status": dependency_status,
            }
        )
        uncertainty_rows.append(
            {
                "claim_id": claim_id,
                "comparison_id": comparison_id,
                "uncertainty_method": "descriptive_only",
                "effect_variation": math.nan,
                "minimum_number_of_blocks_met": False,
            }
        )

    dependency_effects = pd.DataFrame(dependency_rows).convert_dtypes()
    dependency_classification = pd.DataFrame(classification_rows).convert_dtypes()
    effect_uncertainty = pd.DataFrame(uncertainty_rows).convert_dtypes()
    dependency_stability_matrix = pd.DataFrame(stability_rows).convert_dtypes()
    estimability_matrix = dependency_effects.loc[:, ["claim_id", "comparison_id", "estimability_status", "environment_id"]].copy()

    for claim in claim_registry.get("claims", []):
        claim_id = str(claim["claim_id"])
        primary_comparison = str(claim["primary_comparison"])
        comparison_effect = dependency_effects.loc[
            dependency_effects["comparison_id"].astype("string").eq(primary_comparison)
        ].copy()
        if comparison_effect.empty:
            evidence_status = "NO_EVIDENCE"
            supporting_artifact = pd.NA
            contradicting_artifact = pd.NA
        else:
            effect_row = comparison_effect.iloc[0]
            if str(effect_row["estimability_status"]) == "FULL" and pd.notna(effect_row["effect_value"]) and float(effect_row["effect_value"]) > 0:
                evidence_status = "SUPPORTED"
                supporting_artifact = f"dependency_effects::{primary_comparison}"
                contradicting_artifact = pd.NA
            elif str(effect_row["estimability_status"]) == "PARTIAL":
                evidence_status = "PARTIAL"
                supporting_artifact = pd.NA
                contradicting_artifact = pd.NA
            else:
                evidence_status = "NOT_SUPPORTED"
                supporting_artifact = pd.NA
                contradicting_artifact = f"dependency_effects::{primary_comparison}"
        evidence_rows.append(
            {
                "claim_id": claim_id,
                "primary_comparison": primary_comparison,
                "claim_priority": claim.get("claim_priority", "SECONDARY"),
                "evidence_status": evidence_status,
                "supporting_artifact_ids": supporting_artifact,
                "contradicting_artifact_ids": contradicting_artifact,
                "interpretation_limit": "; ".join(claim.get("interpretation_limit", [])),
            }
        )

    claim_evidence_matrix = pd.DataFrame(evidence_rows).convert_dtypes()
    source_expansion_operational_effects = pd.DataFrame(
        [
            {
                "estimand_id": "OPERATIONAL_EXPANSION",
                "effect_mean": math.nan,
                "effect_variation_across_samples": math.nan,
                "number_of_valid_repetitions": 0,
                "source_class_distribution": pd.NA,
                "source_day_count": pd.NA,
                "source_segment_count": pd.NA,
                "status": "DESCRIPTIVE_ONLY",
            }
        ]
    ).convert_dtypes()
    source_expansion_matched_budget_effects = pd.DataFrame(
        [
            {
                "estimand_id": "MATCHED_SEGMENT_DAY_BUDGET_EXPANSION",
                "effect_mean": math.nan,
                "effect_variation_across_samples": math.nan,
                "number_of_valid_repetitions": 0,
                "source_class_distribution": pd.NA,
                "source_day_count": pd.NA,
                "source_segment_count": pd.NA,
                "status": "DESCRIPTIVE_ONLY",
            }
        ]
    ).convert_dtypes()
    candidate_ambiguity_sets = {
        "ambiguities": [
            {
                "claim_id": str(claim["claim_id"]),
                "observed_pattern": str(claim["statement"]),
                "candidate_explanations": [
                    "representation_difference",
                    "support_collapse",
                    "deployment_shift",
                ],
            }
            for claim in claim_registry.get("claims", [])
        ]
    }
    evidence_updated_ambiguity_sets = {
        "ambiguities": [
            {
                "claim_id": row["claim_id"],
                "status": row["evidence_status"],
                "adjudication_mode": "AUTOMATED_RULE",
                "supporting_artifact_ids": [row["supporting_artifact_ids"]] if pd.notna(row["supporting_artifact_ids"]) else [],
                "contradicting_artifact_ids": [row["contradicting_artifact_ids"]] if pd.notna(row["contradicting_artifact_ids"]) else [],
                "reviewer_note": "Tranche 0 evidence-updated ambiguity only; no physical-causal adjudication.",
                "interpretation_boundary": row["interpretation_limit"],
            }
            for row in claim_evidence_matrix.to_dict(orient="records")
        ]
    }
    failure_attribution_matrix = claim_evidence_matrix.loc[
        :,
        ["claim_id", "evidence_status", "supporting_artifact_ids", "contradicting_artifact_ids", "interpretation_limit"],
    ].copy()
    non_identifiability_report = _render_non_identifiability_report(claim_evidence_matrix)
    return {
        "dependency_effects": dependency_effects,
        "dependency_stability_matrix": dependency_stability_matrix,
        "dependency_classification": dependency_classification,
        "estimability_matrix": estimability_matrix,
        "effect_uncertainty": effect_uncertainty,
        "claim_evidence_matrix": claim_evidence_matrix,
        "source_expansion_operational_effects": source_expansion_operational_effects,
        "source_expansion_matched_budget_effects": source_expansion_matched_budget_effects,
        "candidate_ambiguity_sets": candidate_ambiguity_sets,
        "evidence_updated_ambiguity_sets": evidence_updated_ambiguity_sets,
        "failure_attribution_matrix": failure_attribution_matrix,
        "non_identifiability_report": non_identifiability_report,
    }


def _resolve_effect_metric(metric_row: pd.Series) -> float | object:
    if "fixed_ontology_macro_f1" in metric_row.index and pd.notna(metric_row["fixed_ontology_macro_f1"]):
        return float(metric_row["fixed_ontology_macro_f1"])
    if "supported_class_macro_f1" in metric_row.index and pd.notna(metric_row["supported_class_macro_f1"]):
        return float(metric_row["supported_class_macro_f1"])
    return pd.NA


def _classify_dependency(*, effect_value: float | object, estimability_status: str) -> str:
    if estimability_status == "NONE":
        return "INSUFFICIENT_EVIDENCE"
    if estimability_status == "PARTIAL":
        return "CONFLICTING_EVIDENCE"
    if pd.isna(effect_value):
        return "INSUFFICIENT_EVIDENCE"
    if float(effect_value) > 0.0:
        return "STABLE_CANDIDATE"
    if float(effect_value) == 0.0:
        return "REDUNDANT"
    return "DEPLOYMENT_SENSITIVE"


def _render_non_identifiability_report(claim_evidence_matrix: pd.DataFrame) -> str:
    lines = [
        "# Non-Identifiability Report",
        "",
        "Tranche 0 ambiguity outputs remain evidence-updated only.",
        "",
    ]
    for row in claim_evidence_matrix.to_dict(orient="records"):
        lines.append(
            f"- `{row['claim_id']}`: status=`{row['evidence_status']}`; "
            f"boundary=`{row['interpretation_limit']}`."
        )
    return "\n".join(lines) + "\n"
