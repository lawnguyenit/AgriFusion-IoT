from __future__ import annotations

import pandas as pd
from sklearn.metrics import f1_score


_AGRI_ROWS = (
    ("S0_M_t", "S₀ = Mₜ"),
    ("S1_X_t", "S₁ = Xₜ"),
    ("B_M", "Bₘ = Mₜ + Hᴅ"),
    ("S2_X_t_HM", "S₂ = Xₜ + Hᴅ"),
    ("S3_X_t_HX", "S₃ = Xₜ + Hᴅ + Hᴄ"),
    ("F11_X_t_HX_WX", "F₁₁ = S₃ + W"),
    ("F11_X_HX_WX_T", "F₁₁ + T"),
)

_STUARD_ARMS = (
    ("B_line_plus_all_availability", "B = L + Aₐₗₗ"),
    ("B_plus_soil_values", "B + Sₛₒᵢₗ"),
    ("B_plus_environment_values", "B + Sₑₙᵥ"),
    ("B_plus_all_values", "B + Sₐₗₗ"),
)


def build_paper_agri_table(
    predictions: pd.DataFrame,
    anchor_losses: pd.DataFrame,
    feature_contract: dict[str, object],
) -> pd.DataFrame:
    """Rebuild manuscript Table 2 from the frozen held-out anchor artifacts."""
    online_test = predictions.loc[
        predictions["target_view_id"].eq("temporal_online_3h")
        & predictions["partition"].eq("test")
    ]
    loss_test = anchor_losses.loc[
        anchor_losses["target_view_id"].eq("temporal_online_3h")
        & anchor_losses["partition"].eq("test")
    ]
    representations = feature_contract.get("representations", {})
    rows: list[dict[str, object]] = []
    for representation_id, display_name in _AGRI_ROWS:
        pred = online_test.loc[online_test["representation_id"].eq(representation_id)]
        losses = loss_test.loc[loss_test["representation_id"].eq(representation_id)]
        if pred.empty or losses.empty:
            raise ValueError(f"Frozen artifact is missing Table 2 representation {representation_id!r}.")
        fold_scores = [
            f1_score(group["label_online"], group["label_pred"], average="macro")
            for _, group in pred.groupby("fold_id", sort=True)
        ]
        representation = representations.get(representation_id, {})
        rows.append(
            {
                "representation": display_name,
                "representation_id": representation_id,
                "features": int(representation["feature_count"]),
                "log_loss": float(losses["log_loss"].mean()),
                "macro_f1_mean_across_folds": float(sum(fold_scores) / len(fold_scores)),
                "fold_count": int(pred["fold_id"].nunique()),
                "anchor_count": int(pred["sample_id"].nunique()),
            }
        )
    return pd.DataFrame(rows)


def build_paper_uci_table(metrics: pd.DataFrame) -> pd.DataFrame:
    """Rebuild manuscript Table 3 from the frozen test metric summary."""
    rows = metrics.loc[
        metrics["dataset_id"].eq("uci_air_quality") & metrics["partition"].eq("test")
    ].copy()
    rows["head"] = rows["target_id"].map(
        {
            "label_co_q20_tau120m": "CO",
            "label_nox_q20_tau120m": "NOx",
        }
    )
    rows = rows.loc[rows["head"].notna()]
    if set(rows["head"]) != {"CO", "NOx"}:
        raise ValueError("Frozen artifact must contain test metrics for both UCI heads.")
    result = rows.rename(
        columns={
            "positive_prevalence": "prevalence",
            "balanced_accuracy": "balanced_accuracy",
            "roc_auc": "roc_auc",
            "average_precision_positive": "average_precision",
            "log_loss": "log_loss",
        }
    )[["head", "prevalence", "balanced_accuracy", "roc_auc", "average_precision", "log_loss"]]
    return result.sort_values("head", key=lambda col: col.map({"CO": 0, "NOx": 1})).reset_index(drop=True)


def build_paper_stuard_table(metrics: pd.DataFrame, contrasts: pd.DataFrame) -> pd.DataFrame:
    """Rebuild manuscript Table 4 from frozen nested Stuard test controls."""
    test_metrics = metrics.loc[
        metrics["partition"].eq("test")
        & metrics["target"].eq("label_soil_moisture_low_q10_tau1440m")
    ]
    test_contrasts = contrasts.loc[contrasts["partition"].eq("test")]
    contrast_by_arm = test_contrasts.set_index("augmented_arm")
    rows: list[dict[str, object]] = []
    for arm, display_name in _STUARD_ARMS:
        matched = test_metrics.loc[test_metrics["arm"].eq(arm)]
        if len(matched) != 1:
            raise ValueError(f"Expected one Stuard test metric row for {arm!r}; found {len(matched)}.")
        metric = matched.iloc[0]
        contrast = contrast_by_arm.loc[arm] if arm in contrast_by_arm.index else None
        rows.append(
            {
                "arm": display_name,
                "arm_id": arm,
                "log_loss": float(metric["log_loss"]),
                "delta_log_loss_vs_base": float(contrast["delta_log_loss_baseline_minus_augmented"])
                if contrast is not None
                else None,
                "ci_low": float(contrast["delta_log_loss_ci_low"]) if contrast is not None else None,
                "ci_high": float(contrast["delta_log_loss_ci_high"]) if contrast is not None else None,
                "cluster_count": int(contrast["cluster_count"]) if contrast is not None else None,
            }
        )
    return pd.DataFrame(rows)
