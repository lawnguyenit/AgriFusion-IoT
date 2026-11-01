"""Operational END, marginal feasibility, and raw-key cohort checks."""
import numpy as np


def end_labels(states, k=3):
    z = np.asarray(states, dtype=np.int8)
    if k < 1 or not np.isin(z, [0, 1]).all():
        raise ValueError("END requires a binary reference and positive K")
    y = np.zeros(len(z), dtype=np.int8)
    # Direct conjunction deliberately independent of the DP transition code.
    for t in range(k, len(z)):
        y[t] = int(z[t] == 0 and np.all(z[t-k:t] == 1))
    return y


def marginal_labels(observed, k=3, budget=0):
    """Sharp label-wise possibilities; product relaxation drops shared budget."""
    o = np.asarray(observed, dtype=np.int8)
    if budget < 0 or not np.isin(o, [-1, 0, 1]).all():
        raise ValueError("Invalid states/budget")
    lower = np.zeros(len(o), dtype=float)
    upper = np.zeros(len(o), dtype=float)
    complete = np.zeros(len(o), dtype=bool)
    if len(o) > k:
        w = np.lib.stride_tricks.sliding_window_view(o, k+1)
        complete[k:] = np.all(w >= 0, axis=1)
        cost_one = np.sum(w[:, :-1] == 0, axis=1) + (w[:, -1] == 1)
        cost_zero = complete[k:] & (cost_one == 0)
        upper[k:] = cost_one <= budget
        lower[k:] = cost_zero.astype(int) > budget
    known = np.where(lower == upper, lower, np.nan)
    return lower, upper, known, complete


def assert_disjoint_keys(segments):
    owners = {}
    for segment in segments:
        for key in segment.keys:
            key = str(key)
            if key in owners:
                raise ValueError(f"Canonical key occurs in multiple segments: {key}")
            owners[key] = (segment.partition, segment.entity)
    return len(owners)
