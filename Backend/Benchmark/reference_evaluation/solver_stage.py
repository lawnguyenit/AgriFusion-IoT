"""One immutable checkpoint per generic solve, including time-limit results."""
import json
from .evaluation import load_inputs, primary_sensitivity
from .solver import solve_primary


def solve_case(store, case_dir):
    identity = json.loads((case_dir / "case_identity.json").read_text())
    if identity["training_mask_seed"] != 11 or identity["mask_seed"] != 11 or identity["policy"] not in ("mcar30", "block30"):
        return []
    inputs = load_inputs(case_dir / "selection_inputs.npz")
    settings = store.config["generic_solver"]; k = store.config["time_grid_and_target"]["K"]
    expected = {r["R_global"]: r for r in primary_sensitivity(inputs, settings["R_grid"], k)}
    paths = []
    for budget in settings["R_grid"]:
        for direction in settings["directions"]:
            key = "__".join(str(identity[x]) for x in ("dataset_id", "training_mask_seed", "policy", "mask_seed")) + f"__R{budget}__{direction}"
            with store.unit("solver", key, parents=(case_dir / "READY.json",),
                            extra={"R": budget, "direction": direction}) as run:
                if not run.reused:
                    record = solve_primary(inputs, budget, direction, k, settings["time_limit_seconds_per_solve"], settings["mip_rel_gap"])
                    dp = expected[budget]["joint_lower" if direction == "min" else "joint_upper"]
                    record["dp_value"] = dp
                    record["optimal_absolute_error"] = abs(record["incumbent_value"]-dp) if record["status"] == 0 and record["incumbent_value"] is not None else None
                    if record["status"] == 0 and (record["optimal_absolute_error"] is None or record["optimal_absolute_error"] > 1e-8):
                        raise AssertionError("MILP optimum disagrees with independent DP")
                    record = {**identity, "partition": "selection", **record}
                    run.csv("generic_solver_results.csv", [record]); run.json("solver_result.json", record)
                    run.accept(["generic_solver_results.csv", "solver_result.json"], record,
                               f"# Generic solve {key}\n\nStatus: {record['status']}. "
                               f"Incumbent: {record['incumbent_value']}; conservative {record['conservative_bound_role']} bound: {record['conservative_bound']}.\n"
                               "Time limits are retained; an incumbent is not silently treated as a proven extremum.")
            paths.append(run.path)
    return paths
