"""P5: fixed-score reference uncertainty and predeclared corruption stress."""
import json
import numpy as np
import pandas as pd
from .contracts import MODELS
from .decisions import oriented_interval
from .evaluation import load_inputs, primary_sensitivity, corrupt_observed
from .masking import stable_seed


def _true_delta(case_dir, partition):
    risks = pd.read_csv(case_dir / "model_risks.csv")
    subset = risks.loc[risks.partition == partition].set_index("model").true_brier_audit
    return float(subset["SOFT_EM_HGB"]-subset["COMPLETE_HGB"])


def _breakpoint(rows):
    first = rows[0]["verdict"]
    if first == "INCONCLUSIVE":
        return {"baseline_verdict": first, "first_tested_loss": None, "reason": "no baseline certificate"}
    previous = rows[0]["R_global"]
    for row in rows[1:]:
        if row["verdict"] != first:
            if row["verdict"] != "INCONCLUSIVE":
                raise AssertionError("An expanding feasible set reversed a strict certificate")
            return {"baseline_verdict": first, "breakpoint_lower_exclusive": previous,
                    "first_tested_loss": row["R_global"],
                    "exact_minimum_known": row["R_global"]-previous == 1}
        previous = row["R_global"]
    return {"baseline_verdict": first, "minimum_exceeds": previous, "first_tested_loss": None}


def sensitivity_case(store, case_dir):
    identity = json.loads((case_dir / "case_identity.json").read_text())
    key = "__".join(str(identity[k]) for k in ("dataset_id", "training_mask_seed", "policy", "mask_seed"))
    with store.unit("sensitivity", key, parents=(case_dir / "READY.json",)) as run:
        if not run.reused:
            config = store.config; k = config["time_grid_and_target"]["K"]
            tol = config["comparison"]["numerical_tolerance"]
            original_pairs = pd.read_csv(case_dir / "pair_bounds.csv")
            rows = []; corrupted = []; breakpoints = {}; corruption_audit = []
            for partition in ("selection", "assessment"):
                inputs = load_inputs(case_dir / (partition + "_inputs.npz"))
                delta = _true_delta(case_dir, partition)
                curve = primary_sensitivity(inputs, config["reference_error_sensitivity"]["R_grid"], k, tol)
                expected = oriented_interval(original_pairs.loc[original_pairs.partition == partition].to_dict("records"),
                                             "SOFT_EM_HGB", "COMPLETE_HGB")
                if max(abs(curve[0]["joint_lower"]-expected[0]), abs(curve[0]["joint_upper"]-expected[1])) > 1e-9:
                    raise AssertionError("Sensitivity R0 does not recover the original paired interval")
                for row in curve:
                    if not row["joint_lower"]-1e-9 <= delta <= row["joint_upper"]+1e-9:
                        raise AssertionError("Clean recorded truth escaped a declared error set")
                    rows.append({**identity, "partition": partition, **row, "true_delta_audit": delta,
                                 "actual_reference_errors_audit": 0, "inside_contract": True})
                breakpoints[partition] = _breakpoint(curve)
                stress_eligible = identity["training_mask_seed"] == 11 and identity["mask_seed"] == 11 and identity["policy"] in ("mcar30", "block30")
                if not stress_eligible:
                    continue
                with np.load(case_dir / "audit_only" / (partition + "_truth.npz"), allow_pickle=False) as z:
                    full_states = z["F"].copy()
                for count in config["synthetic_corruption_stress"]["C_grid"]:
                    seed = stable_seed(config["study_id"], identity, partition, count, "reference-corruption-v1")
                    changed, locations = corrupt_observed(inputs, count, seed)
                    observed = np.concatenate([s.observed for s in changed])
                    actual = int(np.sum((observed >= 0) & (observed != full_states)))
                    if actual != count:
                        raise AssertionError("Synthetic observed-state corruption count differs from contract")
                    corruption_audit.append({"partition": partition, "C": count, "seed": seed,
                                             "locations_audit_only": locations, "actual_errors": actual})
                    for row in primary_sensitivity(changed, config["synthetic_corruption_stress"]["R_grid"], k, tol):
                        inside = row["R_global"] >= actual
                        contained = row["joint_lower"]-1e-9 <= delta <= row["joint_upper"]+1e-9
                        if inside and not contained:
                            raise AssertionError("Truth escaped a budget containing actual corruptions")
                        corrupted.append({**identity, "partition": partition, "C_actual_audit": actual, **row,
                                          "inside_contract": inside, "truth_in_bounds_audit": contained,
                                          "true_delta_audit": delta})
            run.csv("reference_error_sensitivity.csv", rows)
            run.csv("synthetic_corruption.csv", corrupted,
                    None if corrupted else ["dataset_id", "partition", "C_actual_audit", "R_global", "inside_contract"])
            run.json("breakpoints.json", breakpoints)
            run.json("corruption_audit.json", corruption_audit)
            run.accept(["reference_error_sensitivity.csv", "synthetic_corruption.csv", "breakpoints.json"],
                       {"ordinary_intervals": len(rows), "corruption_intervals": len(corrupted)},
                       f"# Reference sensitivity: {key}\n\nScores were frozen across budgets and corruption. "
                       f"{len(rows)} ordinary intervals; {len(corrupted)} specified corruption intervals.\n"
                       "Breakpoints use grid brackets; R is a global assumed binary-state error budget, not a sensor error estimate.")
    return run.path
