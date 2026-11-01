"""Selection sees estimates/certificates, not full-reference risks or futures."""
from .contracts import MODELS, verdict


def oriented_interval(rows, a, b):
    for r in rows:
        if r["model_a"] == a and r["model_b"] == b:
            return r["joint_lower"], r["joint_upper"]
        if r["model_a"] == b and r["model_b"] == a:
            return -r["joint_upper"], -r["joint_lower"]
    raise ValueError(f"Missing pair {a}/{b}")


def selection_rules(pair_rows, point_rows, development_default, tolerance=1e-12):
    if development_default not in MODELS:
        raise ValueError("Development default is outside the locked pool")
    rows = [{"selection_rule": "always_"+m, "selected_model": m,
             "certificate": "NOT_APPLICABLE", "fallback_model": None} for m in MODELS]
    rows.append({"selection_rule": "development_only", "selected_model": development_default,
                 "certificate": "NOT_APPLICABLE", "fallback_model": None})
    for estimator in ("complete_case", "logically_known", "iid_prior", "markov_expected"):
        values = {r["model"]: r["estimated_risk"] for r in point_rows if r["estimator"] == estimator}
        eligible = [m for m in MODELS if values.get(m) is not None]
        chosen = min(eligible, key=lambda m: (values[m], MODELS.index(m))) if eligible else None
        rows.append({"selection_rule": estimator, "selected_model": chosen,
                     "certificate": "NOT_APPLICABLE", "fallback_model": None})
    a, b = "SOFT_EM_HGB", "COMPLETE_HGB"
    lo, hi = oriented_interval(pair_rows, a, b)
    v = verdict(lo, hi, tolerance)
    chosen = a if v == "A_BETTER" else (b if v == "B_BETTER" else None)
    rows.append({"selection_rule": "pair_joint_three_way", "selected_model": chosen,
                 "certificate": v, "fallback_model": None})
    for fallback in (b, a):
        rows.append({"selection_rule": "pair_joint_fallback_"+fallback,
                     "selected_model": chosen if chosen else fallback,
                     "certificate": v, "fallback_model": fallback if chosen is None else None})
    winners = []
    for model in MODELS:
        if all(oriented_interval(pair_rows, model, other)[1] < -tolerance for other in MODELS if other != model):
            winners.append(model)
    if len(winners) > 1:
        raise AssertionError("Contradictory certified pool winners")
    winner = winners[0] if winners else None
    certificate = "CERTIFIED_WINNER" if winner else "INCONCLUSIVE"
    rows.append({"selection_rule": "pool_joint_three_way", "selected_model": winner,
                 "certificate": certificate, "fallback_model": None})
    rows.append({"selection_rule": "pool_joint_development_fallback", "selected_model": winner or development_default,
                 "certificate": certificate, "fallback_model": None if winner else development_default})
    return rows
