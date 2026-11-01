"""Audit-only joins are downstream of fixed-score evaluation and selection."""
import numpy as np
from .contracts import MODELS
from .targets import end_labels


def true_risks(inputs, reference_segments, k=3):
    lookup = {s.segment_id: s for s in reference_segments}
    sums = np.zeros(len(MODELS)); positive_sums = np.zeros(len(MODELS))
    negative_sums = np.zeros(len(MODELS)); n = positives = 0
    labels = []
    for s in inputs:
        reference = lookup[s.segment_id]
        if not np.array_equal(s.keys, reference.keys) or not np.array_equal(s.score, reference.score):
            raise AssertionError("Audit/forecast cohort keys differ")
        y = end_labels(reference.states, k)
        loss = (s.probabilities-y)**2
        sums += loss[:, s.score].sum(axis=1)
        positive_sums += loss[:, s.score & (y == 1)].sum(axis=1)
        negative_sums += loss[:, s.score & (y == 0)].sum(axis=1)
        n += int(s.score.sum()); positives += int(y[s.score].sum()); labels.append(y)
    if not n:
        raise ValueError("Empty audit cohort")
    return [{"model": m, "true_brier_audit": float(sums[i]/n), "n_scored": n,
             "END_positives_audit": positives, "END_negatives_audit": n-positives,
             "positive_mean_brier_audit": float(positive_sums[i]/positives) if positives else None,
             "negative_mean_brier_audit": float(negative_sums[i]/(n-positives)) if n > positives else None,
             "positive_weighted_brier_audit": float(positive_sums[i]/n),
             "negative_weighted_brier_audit": float(negative_sums[i]/n)} for i, m in enumerate(MODELS)], labels


def check_certificates(rows, risks, tolerance=1e-9):
    risk = {r["model"]: r["true_brier_audit"] for r in risks}
    checks = []
    for r in rows:
        delta = risk[r["model_a"]]-risk[r["model_b"]]
        contained = r["joint_lower"]-tolerance <= delta <= r["joint_upper"]+tolerance
        if not contained:
            raise AssertionError("Recorded truth is outside R0 joint bounds")
        checks.append({"model_a": r["model_a"], "model_b": r["model_b"],
                       "true_delta_audit": delta, "truth_in_bounds": contained})
    return checks


def attach_decision_outcomes(choices, selection_risks, assessment_risks):
    selection = {r["model"]: r["true_brier_audit"] for r in selection_risks}
    future = {r["model"]: r["true_brier_audit"] for r in assessment_risks}
    result = []
    for choice in choices:
        model = choice["selected_model"]
        result.append({**choice, "selection_n": selection_risks[0]["n_scored"],
                       "selection_regret_audit": selection[model]-min(selection.values()) if model else None,
                       "assessment_n": assessment_risks[0]["n_scored"],
                       "assessment_brier_audit": future.get(model),
                       "assessment_regret_audit": future[model]-min(future.values()) if model else None})
    return result
