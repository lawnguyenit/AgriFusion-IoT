"""Comparison methods operate on public EvaluationSegment objects only."""
from itertools import combinations
import hashlib
import numpy as np
from .bounds import pool_bounds
from .contracts import MODELS, EvaluationSegment, verdict, comparison_reason
from .markov import end_marginals
from .targets import marginal_labels


def input_fingerprints(inputs):
    p_hash = hashlib.sha256(); key_hash = hashlib.sha256()
    for s in inputs:
        s.validate()
        p_hash.update(np.asarray(s.probabilities, dtype="<f8").tobytes())
        for key in s.keys[s.score]:
            key_hash.update(str(key).encode()); key_hash.update(b"\0")
    return p_hash.hexdigest(), key_hash.hexdigest()


def compare_pool(inputs, transition, prior, state_prevalence, k=3, tolerance=1e-12):
    """All pairs at R0; point estimates and constraints share the same inputs."""
    for segment in inputs:
        segment.validate()
    n = sum(int(s.score.sum()) for s in inputs)
    if not n:
        raise ValueError("Empty scored pool")
    pairs = list(combinations(range(len(MODELS)), 2))
    constants = np.zeros(len(MODELS)); rectangles = np.zeros((len(pairs), 2))
    weights = []; totals = {name: np.zeros(len(MODELS)) for name in
                            ("complete_case", "logically_known", "iid_prior", "markov_expected")}
    denominators = {name: 0 for name in totals}
    known_positive = complete_positive = 0
    for s in inputs:
        p = s.probabilities; score = s.score
        constants += (p[:, score]**2).sum(axis=1)
        lo, hi, known, complete = marginal_labels(s.observed, k)
        w_pair = np.stack([-2*(p[a]-p[b])*score for a, b in pairs])
        weights.append(np.vstack((w_pair, (1-2*p)*score)))
        rectangles[:, 0] += np.minimum(w_pair*lo, w_pair*hi).sum(axis=1)
        rectangles[:, 1] += np.maximum(w_pair*lo, w_pair*hi).sum(axis=1)
        posterior = end_marginals(s.observed, transition, prior, k)
        q = np.where(s.observed < 0, state_prevalence, s.observed).astype(float)
        iid = np.zeros(len(q))
        for t in range(k, len(q)):
            iid[t] = np.prod(q[t-k:t])*(1-q[t])
        for name, target, use in (
                ("complete_case", known, score & complete),
                ("logically_known", known, score & np.isfinite(known)),
                ("iid_prior", iid, score),
                ("markov_expected", posterior, score)):
            totals[name] += (p[:, use]**2 - 2*p[:, use]*target[use] + target[use]).sum(axis=1)
            denominators[name] += int(use.sum())
        known_positive += int(np.sum(score & (known == 1)))
        complete_positive += int(np.sum(score & complete & (known == 1)))
    low, high = pool_bounds([s.observed for s in inputs], weights, k, 0)
    low, high = low[:, 0], high[:, 0]
    risk_lo = (constants + low[len(pairs):])/n
    risk_hi = (constants + high[len(pairs):])/n
    p_hash, cohort_hash = input_fingerprints(inputs)
    rows = []
    for j, (a, b) in enumerate(pairs):
        base = (constants[a]-constants[b])/n
        jl, ju = base+low[j]/n, base+high[j]/n
        rl, ru = base+rectangles[j, 0]/n, base+rectangles[j, 1]/n
        sl, su = risk_lo[a]-risk_hi[b], risk_hi[a]-risk_lo[b]
        if jl < rl-1e-10 or ju > ru+1e-10 or jl < sl-1e-10 or ju > su+1e-10:
            raise AssertionError("Joint interval is outside a matching outer bound")
        rows.append({"model_a": MODELS[a], "model_b": MODELS[b], "n_scored": n,
                     "joint_lower": float(jl), "joint_upper": float(ju),
                     "rectangle_lower": float(rl), "rectangle_upper": float(ru),
                     "separate_lower": float(sl), "separate_upper": float(su),
                     "verdict": verdict(jl, ju, tolerance), "reason": comparison_reason(jl,ju,tolerance), "prediction_sha256": p_hash,
                     "cohort_sha256": cohort_hash, "R_global": 0})
    points = []
    for name, total in totals.items():
        for j, model in enumerate(MODELS):
            den = denominators[name]
            points.append({"estimator": name, "model": model,
                           "estimated_risk": float(total[j]/den) if den else None,
                           "n_used": den, "n_scored": n})
    info = {"n_scored": n, "known_labels": denominators["logically_known"],
            "complete_labels": denominators["complete_case"],
            "known_positive_END": known_positive, "complete_positive_END": complete_positive,
            "prediction_sha256": p_hash, "cohort_sha256": cohort_hash}
    return rows, points, info


def primary_sensitivity(inputs, budgets, k=3, tolerance=1e-12):
    for s in inputs:
        s.validate()
    a, b = MODELS.index("SOFT_EM_HGB"), MODELS.index("COMPLETE_HGB")
    n = sum(int(s.score.sum()) for s in inputs)
    if not n:
        raise ValueError("Empty sensitivity cohort")
    constant = sum(float(((s.probabilities[a]**2-s.probabilities[b]**2)*s.score).sum()) for s in inputs)/n
    weights = [-2*(s.probabilities[a]-s.probabilities[b])*s.score for s in inputs]
    lo, hi = pool_bounds([s.observed for s in inputs], weights, k, max(budgets))
    p_hash, cohort_hash = input_fingerprints(inputs)
    observed_count = sum(int((s.observed >= 0).sum()) for s in inputs)
    result = []
    for budget in sorted(set(budgets)):
        lower, upper = constant+lo[0, budget]/n, constant+hi[0, budget]/n
        result.append({"model_a": MODELS[a], "model_b": MODELS[b], "R_global": int(budget),
                       "joint_lower": float(lower), "joint_upper": float(upper),
                       "verdict": verdict(lower, upper, tolerance), "reason": comparison_reason(lower,upper,tolerance), "n_scored": n,
                       "n_observed": observed_count, "R_per_observed": budget/observed_count if observed_count else None,
                       "prediction_sha256": p_hash, "cohort_sha256": cohort_hash})
    for left, right in zip(result, result[1:]):
        if right["joint_lower"] > left["joint_lower"]+1e-10 or right["joint_upper"] < left["joint_upper"]-1e-10:
            raise AssertionError("Error-budget bounds are not nested")
    return result


def corrupt_observed(inputs, count, seed):
    indexes = [(i, int(j)) for i, s in enumerate(inputs) for j in np.flatnonzero(s.observed >= 0)]
    if count > len(indexes) or count < 0:
        raise ValueError("Corruption count exceeds observed reference")
    picked = np.random.default_rng(seed).choice(len(indexes), size=count, replace=False)
    arrays = [s.observed.copy() for s in inputs]
    locations = [indexes[int(j)] for j in picked]
    for i, j in locations:
        arrays[i][j] = 1-arrays[i][j]
    changed = [EvaluationSegment(s.segment_id, s.keys, o, s.score, s.probabilities)
               for s, o in zip(inputs, arrays)]
    if input_fingerprints(changed) != input_fingerprints(inputs):
        raise AssertionError("Corrupting reference changed forecast/cohort")
    return changed, locations


def save_inputs(path, inputs):
    offsets = np.r_[0, np.cumsum([len(s.observed) for s in inputs])]
    np.savez_compressed(path, observed=np.concatenate([s.observed for s in inputs]),
                        schema_version=np.array("csv_npz_v1"),model_order=np.array(MODELS),
                        score=np.concatenate([s.score for s in inputs]),
                        keys=np.concatenate([s.keys for s in inputs]).astype(str),
                        probabilities=np.concatenate([s.probabilities for s in inputs], axis=1),
                        offsets=offsets, segment_ids=np.array([s.segment_id for s in inputs], dtype=str))


def load_inputs(path):
    with np.load(path, allow_pickle=False) as z:
        data = {name: z[name] for name in z.files}
        if str(data.get('schema_version',''))!='csv_npz_v1' or tuple(data.get('model_order',()))!=MODELS:
            raise ValueError('Unknown input schema or probability model order')
        result = []
        for i, sid in enumerate(data["segment_ids"]):
            a, b = data["offsets"][i:i+2]; sl = slice(a, b)
            s = EvaluationSegment(str(sid), data["keys"][sl].copy(), data["observed"][sl].copy(),
                                  data["score"][sl].copy(), data["probabilities"][:, sl].copy())
            s.validate(); result.append(s)
    return result
