"""Fit once from visible training data; fixed candidate pool, no HPO."""
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from .contracts import MODELS, EvaluationSegment, FailedSupport
from .features import causal_features
from .markov import fit_markov, end_marginals, causal_forecast
from .masking import mask_observations
from .targets import marginal_labels


def _binary_classes(y, name):
    if len(y) == 0 or set(np.unique(y)) != {0, 1}:
        raise FailedSupport(f"{name} lacks two effective training classes; no silent constant substitution")


def fit_candidates(segments, config, source_id, training_seed):
    train = [s for s in segments if s.partition == "train"]
    if not train:
        raise FailedSupport("No training segments")
    k = config["time_grid_and_target"]["K"]
    warmup = config["time_grid_and_target"]["warmup_per_segment"]
    observed = []; visible = []; effective = []
    for s in train:
        o, x, m, seed = mask_observations(s, "mcar30", config["study_id"], source_id,
                                         training_seed, training_seed, warmup)
        observed.append(o); visible.append(x)
        effective.append({"segment_id": s.segment_id, "effective_seed": seed,
                          "hidden_count": int(m.sum())})
    values = np.concatenate(visible); values = values[np.isfinite(values)]
    if not len(values):
        raise FailedSupport("No observed training values")
    median = float(np.median(values)); scale = float(np.std(values))
    if scale <= 0:
        raise FailedSupport("Observed training signal has zero scale")
    settings = config["training"]["markov_EM"]
    a, pi, trace = fit_markov(observed, settings["max_iterations"], settings["tolerance"],
                            settings["transition_pseudocount"])
    x6 = []; x24 = []; hard = []; soft = []; hard_keep = []
    for s, o, x in zip(train, observed, visible):
        _, _, known, complete = marginal_labels(o, k)
        x6.append(causal_features(x, 6, median, scale)[s.score])
        x24.append(causal_features(x, 24, median, scale)[s.score])
        hard.append(known[s.score]); soft.append(end_marginals(o, a, pi, k)[s.score])
        hard_keep.append(complete[s.score])
    x6 = np.concatenate(x6); x24 = np.concatenate(x24)
    hard = np.concatenate(hard); soft = np.concatenate(soft); keep = np.concatenate(hard_keep)
    y = hard[keep].astype(np.int8); _binary_classes(y, "COMPLETE")
    common = dict(config["training"]["hgb"], random_state=int(training_seed))
    complete = HistGradientBoostingClassifier(**common).fit(x6[keep], y)
    duplicated = np.concatenate((x6, x6)); labels = np.r_[np.zeros(len(soft)), np.ones(len(soft))]
    weights = np.r_[1-soft, soft]; positive_weight = weights > 0
    _binary_classes(labels[positive_weight], "SOFT_EM")
    em_model = HistGradientBoostingClassifier(**common).fit(
        duplicated[positive_weight], labels[positive_weight], sample_weight=weights[positive_weight])
    long_model = HistGradientBoostingClassifier(**common).fit(x24[keep], y)
    lr = config["training"]["LOGISTIC_COMPLETE_H6"]
    logistic = LogisticRegression(C=lr["C"], max_iter=lr["max_iter"], class_weight=None,
                                  random_state=int(training_seed)).fit(x6[keep], y)
    flat_observed = np.concatenate(observed)
    return {"model_order": list(MODELS), "median": median, "scale": scale, "transition": a,
            "prior": pi, "state_prevalence": float(flat_observed[flat_observed >= 0].mean()),
            "constant": float(y.mean()), "training_mask_seed": int(training_seed),
            "models": {"COMPLETE_HGB": complete, "SOFT_EM_HGB": em_model,
                       "LOGISTIC_COMPLETE_H6": logistic, "HGB_COMPLETE_H24": long_model},
            "fit_metadata": {"supervised_fits": 4, "HGB_fits": 3,
                             "complete_training_origins": int(keep.sum()),
                             "soft_training_origins": len(soft), "complete_positive_END": int(y.sum()),
                             "markov_log_likelihood": trace, "effective_masks": effective}}


def predict_segment(segment_id, keys, score, bundle, observed, visible, k=3):
    x6 = causal_features(visible, 6, bundle["median"], bundle["scale"])
    x24 = causal_features(visible, 24, bundle["median"], bundle["scale"])
    p = np.empty((len(MODELS), len(observed)))
    for i, name in enumerate(MODELS):
        if name == "MARKOV":
            p[i] = causal_forecast(observed, bundle["transition"], bundle["prior"], k)
        elif name == "CONSTANT":
            p[i] = bundle["constant"]
        else:
            model = bundle["models"][name]
            if list(model.classes_) != [0, 1]:
                raise ValueError(f"Unexpected binary class order for {name}")
            x = x24 if name == "HGB_COMPLETE_H24" else x6
            p[i] = model.predict_proba(x)[:, 1]
    result = EvaluationSegment(segment_id, keys, observed, score, p)
    result.validate()
    return result


def make_inputs(segments, bundle, config, source_id, policy, mask_seed):
    result = []; mask_rows = []
    for s in segments:
        o, x, m, seed = mask_observations(s, policy, config["study_id"], source_id,
                                         bundle["training_mask_seed"], mask_seed,
                                         config["time_grid_and_target"]["warmup_per_segment"])
        result.append(predict_segment(s.segment_id, s.keys, s.score, bundle, o, x,
                                      config["time_grid_and_target"]["K"]))
        mask_rows.append({"segment_id": s.segment_id, "partition": s.partition, "policy": policy,
                          "mask_seed": mask_seed, "effective_seed": seed, "states": len(m),
                          "observed_states": int((~m).sum()), "hidden_scored": int(m[s.score].sum()),
                          "scored_origins": int(s.score.sum())})
    return result, mask_rows
