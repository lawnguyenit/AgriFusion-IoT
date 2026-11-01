"""Standard finite-state min/max inference, with one pooled error budget.

The END/run-state formulation follows the delivered pilot reference; this
generalization removes its fixed 70-row/2022/2023 assumptions. No novelty claim.
"""
import numpy as np


def segment_frontier(observed, weights, k=3, max_r=0):
    """Return min/max sum(w*END) for each EXACT observed-state error count.

    weights may have shape [time] or [objectives,time]. Memory is rolling
    O(objectives*K*R). First K labels are zero; scored warmup must be >= K.
    """
    o = np.asarray(observed, dtype=np.int8)
    w = np.asarray(weights, dtype=float)
    scalar = w.ndim == 1
    if scalar:
        w = w[None, :]
    if w.ndim != 2 or w.shape[1] != len(o) or max_r < 0 or k < 1:
        raise ValueError("Invalid DP shape/K/budget")
    if not np.isin(o, [-1, 0, 1]).all() or not np.isfinite(w).all():
        raise ValueError("Invalid DP observations/weights")
    p = len(w)
    lo = np.full((p, k+1, max_r+1), np.inf)
    hi = np.full_like(lo, -np.inf)
    lo[:, 0, 0] = hi[:, 0, 0] = 0.0
    for t, obs in enumerate(o):
        nl = np.full_like(lo, np.inf)
        nh = np.full_like(hi, -np.inf)
        for bit in (0, 1):
            cost = int(obs >= 0 and bit != obs)
            if cost > max_r:
                continue
            source = slice(0, max_r+1-cost)
            dest = slice(cost, max_r+1)
            for state in range(k+1):
                new_state = min(k, state+1) if bit else 0
                event_cost = w[:, t, None] if state == k and bit == 0 else 0.0
                np.minimum(nl[:, new_state, dest], lo[:, state, source] + event_cost,
                           out=nl[:, new_state, dest])
                np.maximum(nh[:, new_state, dest], hi[:, state, source] + event_cost,
                           out=nh[:, new_state, dest])
        lo, hi = nl, nh
    a, b = lo.min(axis=1), hi.max(axis=1)
    return (a[0], b[0]) if scalar else (a, b)


def _convolve(left, right, minimize):
    n = left.shape[-1]
    out = np.full_like(left, np.inf if minimize else -np.inf)
    op = np.minimum if minimize else np.maximum
    for r in range(n):
        values = left[..., :r+1] + right[..., r::-1]
        out[..., r] = values.min(axis=-1) if minimize else values.max(axis=-1)
    return out


def pool_bounds(observations, weights, k=3, max_r=0):
    """Global at-most-R extrema, not an independent R allowance per segment."""
    if not observations or len(observations) != len(weights):
        raise ValueError("A nonempty matching segment collection is required")
    n_obj = 1 if np.asarray(weights[0]).ndim == 1 else len(weights[0])
    lo = np.full((n_obj, max_r+1), np.inf)
    hi = np.full_like(lo, -np.inf)
    lo[:, 0] = hi[:, 0] = 0
    for obs, w in zip(observations, weights):
        a, b = segment_frontier(obs, w, k, max_r)
        lo = _convolve(lo, np.atleast_2d(a), True)
        hi = _convolve(hi, np.atleast_2d(b), False)
    return np.minimum.accumulate(lo, axis=-1), np.maximum.accumulate(hi, axis=-1)
