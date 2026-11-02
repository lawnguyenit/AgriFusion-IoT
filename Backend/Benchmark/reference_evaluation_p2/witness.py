"""Exact-state R0 primary-pair traceback; no access to full truth."""
import numpy as np
from ..reference_evaluation.contracts import MODELS
from ..reference_evaluation.bounds import pool_bounds

PAIR = ('SOFT_EM_HGB', 'COMPLETE_HGB')


def primary_bounds(inputs, k=3):
    for segment in inputs:
        segment.validate()
    a, b = map(MODELS.index, PAIR)
    n = sum(int(s.score.sum()) for s in inputs)
    if not n:
        raise ValueError('Empty scored cohort')
    constant = sum(float(((s.probabilities[a]**2-s.probabilities[b]**2)*s.score).sum()) for s in inputs)/n
    weights = [-2*(s.probabilities[a]-s.probabilities[b])*s.score for s in inputs]
    low, high = pool_bounds([s.observed for s in inputs], weights, k, 0)
    return float(constant+low[0, 0]/n), float(constant+high[0, 0]/n)


def trace_segment(observed, weights, k=3, direction='min'):
    """R=0 only. Deterministic ties keep the first reachable predecessor.

    Stored predecessors cost O(T*K); old rolling DP is left unchanged.
    Float comparisons produce numerical witnesses, not exact-arithmetic proofs.
    """
    o = np.asarray(observed)
    w = np.asarray(weights, dtype=float)
    if k < 1 or direction not in ('min', 'max') or o.ndim != 1 or w.shape != o.shape:
        raise ValueError('Invalid traceback contract')
    if not np.isin(o, [-1, 0, 1]).all() or not np.isfinite(w).all():
        raise ValueError('Invalid observations or objective')
    sign = 1 if direction == 'min' else -1
    costs = np.full(k+1, np.inf); costs[0] = 0
    parents = np.full((len(o), k+1), -1, dtype=np.int32)
    bits = np.full((len(o), k+1), -1, dtype=np.int8)
    for t, obs in enumerate(o):
        next_costs = np.full(k+1, np.inf)
        for state in range(k+1):
            if not np.isfinite(costs[state]):
                continue
            for bit in (0, 1):
                if obs >= 0 and bit != obs:
                    continue
                dest = min(k, state+1) if bit else 0
                value = costs[state] + (sign*w[t] if state == k and bit == 0 else 0)
                if value < next_costs[dest]:
                    next_costs[dest] = value
                    parents[t, dest] = state; bits[t, dest] = bit
        costs = next_costs
    state = int(np.argmin(costs)); optimum = sign*float(costs[state])
    if not np.isfinite(optimum):
        raise ValueError('No feasible completion')
    z = np.empty(len(o), dtype=np.int8)
    for t in range(len(o)-1, -1, -1):
        z[t] = bits[t, state]; state = int(parents[t, state])
    return z, optimum


def trace_pool(inputs, k=3, direction='min', budget=0):
    if budget != 0:
        raise ValueError('P2 pilot traceback supports global R=0 only')
    a, b = map(MODELS.index, PAIR)
    for s in inputs:
        s.validate()
    return [trace_segment(s.observed, -2*(s.probabilities[a]-s.probabilities[b])*s.score,
                          k, direction)[0] for s in inputs]
