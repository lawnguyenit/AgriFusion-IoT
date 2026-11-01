"""Same-information generic MILP; primal and dual bounds remain distinct."""
import time
import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_array
from .contracts import MODELS
from .targets import end_labels


def solve_primary(inputs, budget, direction, k=3, time_limit=10, mip_rel_gap=1e-9):
    if direction not in ("min", "max") or budget < 0:
        raise ValueError("Invalid solver direction/budget")
    for s in inputs:
        s.validate()
    started = time.perf_counter()
    observed = np.concatenate([s.observed for s in inputs])
    n = len(observed); score = np.concatenate([s.score for s in inputs])
    den = int(score.sum())
    if not den:
        raise ValueError("No scored origins")
    a, b = MODELS.index("SOFT_EM_HGB"), MODELS.index("COMPLETE_HGB")
    pa = np.concatenate([s.probabilities[a] for s in inputs])
    pb = np.concatenate([s.probabilities[b] for s in inputs])
    constant = float(((pa**2-pb**2)*score).sum()/den)
    weights = -2*(pa-pb)*score
    ri = []; ci = []; values = []; lows = []; highs = []

    def row(coefficients, lower=-np.inf, upper=np.inf):
        idx = len(lows)
        for col, value in coefficients:
            ri.append(idx); ci.append(col); values.append(value)
        lows.append(lower); highs.append(upper)

    lower = np.zeros(2*n); upper = np.ones(2*n)
    offset = 0
    for s in inputs:
        for t in range(len(s.observed)):
            i = offset+t
            if t < k:
                upper[n+i] = 0; continue
            for j in range(i-k, i):
                row([(n+i, 1), (j, -1)], upper=0)
            row([(n+i, 1), (i, 1)], upper=1)
            row([(n+i, 1), (i, 1)]+[(j, -1) for j in range(i-k, i)], lower=1-k)
        offset += len(s.observed)
    row([(i, 1 if bit == 0 else -1) for i, bit in enumerate(observed) if bit >= 0],
        upper=budget-int((observed == 1).sum()))
    matrix = coo_array((np.asarray(values, float), (np.asarray(ri, np.int32), np.asarray(ci, np.int32))),
                       shape=(len(lows), 2*n)).tocsc()
    sign = 1 if direction == "min" else -1
    objective = np.r_[np.zeros(n), sign*weights]
    build_seconds = time.perf_counter()-started
    result = milp(objective, integrality=np.ones(2*n, dtype=np.uint8),
                  bounds=Bounds(lower, upper), constraints=LinearConstraint(matrix, lows, highs),
                  options={"time_limit": time_limit, "mip_rel_gap": mip_rel_gap})
    incumbent = float(constant+sign*result.fun/den) if result.fun is not None and np.isfinite(result.fun) else None
    dual = getattr(result, "mip_dual_bound", None)
    conservative = float(constant+sign*dual/den) if dual is not None and np.isfinite(dual) else None
    witness_valid = None; witness_errors = None
    if result.x is not None:
        integer_ok = bool(np.max(np.abs(result.x-np.rint(result.x))) <= 1e-5)
        z = np.rint(result.x[:n]).astype(np.int8)
        reported_y = np.rint(result.x[n:]).astype(np.int8)
        actual = []; offset = 0
        for s in inputs:
            actual.append(end_labels(z[offset:offset+len(s.observed)], k)); offset += len(s.observed)
        y = np.concatenate(actual)
        witness_errors = int(np.sum((observed >= 0) & (z != observed)))
        direct = float(constant+weights@y/den)
        witness_valid = bool(integer_ok and np.isin(z, [0, 1]).all() and witness_errors <= budget and
                             np.array_equal(y, reported_y) and incumbent is not None and abs(direct-incumbent) <= 1e-8)
        if not witness_valid:
            raise AssertionError("MILP returned an invalid witness")
    return {"R_global": budget, "direction": direction, "status": int(result.status),
            "message": str(result.message), "incumbent_value": incumbent,
            "conservative_bound": conservative,
            "conservative_bound_role": "lower" if direction == "min" else "upper",
            "mip_gap": float(result.mip_gap) if getattr(result, "mip_gap", None) is not None and np.isfinite(result.mip_gap) else None,
            "mip_gap_nonfinite": bool(getattr(result, "mip_gap", None) is not None and not np.isfinite(result.mip_gap)),
            "witness_valid": witness_valid, "witness_errors": witness_errors,
            "variables": 2*n, "constraints": len(lows), "n_scored": den,
            "build_seconds": build_seconds, "wall_seconds": time.perf_counter()-started}
