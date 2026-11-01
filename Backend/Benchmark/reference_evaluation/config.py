"""Validate scientific choices instead of silently accepting an old profile."""
import json
from pathlib import Path
from .contracts import MODELS, PARTITIONS


def load_config(path):
    config = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    validate_config(config)
    return config


def validate_config(c):
    if tuple(c["scope"]["secondary_pool"]) != MODELS:
        raise ValueError("This implementation requires the declared six-model pool/order")
    if tuple(c["splits"]["partition_order"]) != PARTITIONS:
        raise ValueError("Four ordered partitions are required")
    ratios = c["splits"]["fractions_of_sorted_unique_source_times"]
    if len(ratios) != 4 or min(ratios) <= 0 or abs(sum(ratios)-1) > 1e-12:
        raise ValueError("Invalid four-way split ratios")
    rule = c["time_grid_and_target"]
    if rule["K"] < 1 or rule["warmup_per_segment"] < max(24, rule["K"]):
        raise ValueError("Warmup must cover the largest predeclared feature/target history")
    if rule["threshold"]["comparison"] != "strictly greater":
        raise ValueError("Only the explicit strict-greater rule is implemented")
    if not 0 < rule["threshold"]["quantile"] < 1:
        raise ValueError("Invalid training quantile")
    allowed = {"beijing_multi_site_501", "appliances_energy_374"}
    ids = [s["dataset_id"] for s in c["sources"]]
    if not ids or len(ids) != len(set(ids)) or not set(ids) <= allowed:
        raise ValueError("Use explicit Beijing501/Appliances374 adapters")
    for source in c["sources"]:
        expected = "PM2.5" if source["dataset_id"] == "beijing_multi_site_501" else "RH_1"
        if source["variable"] != expected:
            raise ValueError("Source variable differs from the implemented adapter contract")
    if c["training"]["hpo"] or c["training"]["hgb"]["early_stopping"]:
        raise ValueError("HPO/implicit validation are outside the locked v1 contract")
    if c["training"]["mask_policy"] != "mcar30" or c["training"]["LOGISTIC_COMPLETE_H6"]["class_weight"] is not None:
        raise ValueError("The locked v1 training mask/weighting differs from implementation")
    if c["evaluation_masks"]["policies"][0] != "full_control":
        raise ValueError("Keep a full-control condition")
    for field in ("reference_error_sensitivity", "synthetic_corruption_stress", "generic_solver"):
        grid = c[field]["R_grid"]
        if not grid or min(grid) < 0 or any(int(r) != r for r in grid):
            raise ValueError("Error budgets must be nonnegative integers")
    if c["resources"]["parallel_fit_jobs"] != 1:
        raise ValueError("This storage writer requires a single local fit/orchestrator job")


def cells(config):
    for policy in config["evaluation_masks"]["policies"]:
        seeds = [0] if policy == "full_control" else config["evaluation_masks"]["mask_seeds"]
        for seed in seeds:
            yield policy, int(seed)
