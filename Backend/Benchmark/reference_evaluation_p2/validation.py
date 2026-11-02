"""Independent witness scoring and audit joins; never used by evaluator."""
import numpy as np
from ..reference_evaluation.contracts import MODELS
from .witness import PAIR


def labels(states, k):
    """Vectorized conjunction independent of traceback state transitions."""
    z = np.asarray(states)
    if z.ndim != 1 or not np.isin(z, [0, 1]).all() or k < 1:
        raise ValueError('Invalid witness states/K')
    y = np.zeros(len(z), dtype=np.int8)
    if len(z) > k:
        windows = np.lib.stride_tricks.sliding_window_view(z, k+1)
        y[k:] = (windows[:, :-1] == 1).all(axis=1) & (windows[:, -1] == 0)
    return y


def score_witness(inputs, completions, k, warmup, expected=None, tolerance=1e-9):
    if len(inputs) != len(completions) or not inputs:
        raise ValueError('Witness segment count mismatch')
    a, b = map(MODELS.index, PAIR)
    losses = np.zeros(2); count = errors = 0; all_keys = []; derived = []
    for s, z in zip(inputs, completions):
        s.validate(); z = np.asarray(z)
        if z.shape != s.observed.shape or not np.isin(z, [0, 1]).all():
            raise ValueError('Witness length/binary contract')
        if s.score[:warmup].any():
            raise ValueError('Scored warmup')
        errors += int(((s.observed >= 0) & (z != s.observed)).sum())
        y = labels(z, k); derived.append(y)
        losses += ((s.probabilities[[a, b]][:, s.score]-y[s.score])**2).sum(axis=1)
        count += int(s.score.sum()); all_keys.extend(s.keys.tolist())
    if errors or not count or len(set(all_keys)) != len(all_keys):
        raise ValueError('R0 observation violation, empty or duplicate cohort')
    risks = losses/count; delta = float(risks[0]-risks[1])
    if expected is not None and abs(delta-expected) > tolerance:
        raise ValueError('Witness did not attain original endpoint')
    return {'n_scored':count, 'observed_errors_global':errors, 'R_global':0,
            'brier_a':float(risks[0]), 'brier_b':float(risks[1]), 'objective':delta,
            'expected_endpoint':expected, 'endpoint_absolute_error':abs(delta-expected) if expected is not None else None}, derived


def audit_delta(inputs, reference, k, warmup):
    if len(inputs) != len(reference):
        raise ValueError('Reference segment count mismatch')
    for s, r in zip(inputs, reference):
        if s.segment_id != r.segment_id or not np.array_equal(s.keys, r.keys) or not np.array_equal(s.score, r.score):
            raise ValueError('Audit cohort mismatch')
    result, _ = score_witness(inputs, [r.states for r in reference], k, warmup)
    return result['objective']


def classify(lower, upper, tolerance=1e-12, endpoint_error=0):
    if endpoint_error > tolerance:
        return 'numerically_unresolved'
    if lower < -tolerance and upper > tolerance:
        return 'opposite_strict_orders_attained_float_verified'
    if upper < -tolerance:
        return 'A_strictly_better_within_declared_tolerance'
    if lower > tolerance:
        return 'B_strictly_better_within_declared_tolerance'
    if abs(lower) <= tolerance and abs(upper) <= tolerance:
        return 'tie_within_tolerance'
    if abs(lower) <= tolerance or abs(upper) <= tolerance:
        return 'endpoint_touches_zero_within_tolerance'
    return 'numerically_unresolved'


def recheck_saved(path, inputs, k, warmup, endpoint):
    """Reopen witness bytes; score against the original fixed predictions."""
    with np.load(path,allow_pickle=False) as z:
        expected_offsets=np.r_[0,np.cumsum([len(s.keys) for s in inputs])]
        if str(z['schema_version'])!='p2_witness_r0_v1' or not np.array_equal(z['offsets'],expected_offsets):
            raise ValueError('Saved offsets/schema mismatch')
        for field,expected in [('keys',np.concatenate([s.keys for s in inputs])),
                               ('observed',np.concatenate([s.observed for s in inputs])),
                               ('score',np.concatenate([s.score for s in inputs])),
                               ('segment_ids',np.array([s.segment_id for s in inputs]))]:
            if not np.array_equal(z[field],expected):
                raise ValueError('Saved witness '+field+' mismatch')
        completions=[z['states'][a:b].copy() for a,b in zip(expected_offsets[:-1],expected_offsets[1:])]
        _,derived=score_witness(inputs,completions,k,warmup,endpoint)
        if not np.array_equal(z['END'],np.concatenate(derived)):
            raise ValueError('Saved END differs from independent reconstruction')
    return True
