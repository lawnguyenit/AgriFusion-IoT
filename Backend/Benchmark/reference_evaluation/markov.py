"""Train-only Markov EM, offline END marginals, and causal END forecasts."""
import numpy as np


def forward_backward(observed, transition, prior):
    o = np.asarray(observed, dtype=np.int8)
    if len(o) == 0 or not np.isin(o, [-1, 0, 1]).all():
        raise ValueError("Nonempty -1/0/1 sequence required")
    e = np.column_stack((o != 1, o != 0)).astype(float)
    alpha = np.empty((len(o), 2)); scale = np.empty(len(o))
    alpha[0] = prior * e[0]; scale[0] = alpha[0].sum()
    if scale[0] <= 0:
        raise ValueError("Impossible Markov evidence")
    alpha[0] /= scale[0]
    for t in range(1, len(o)):
        alpha[t] = (alpha[t-1] @ transition) * e[t]
        scale[t] = alpha[t].sum()
        if scale[t] <= 0:
            raise ValueError("Impossible Markov evidence")
        alpha[t] /= scale[t]
    beta = np.ones_like(alpha)
    for t in range(len(o)-2, -1, -1):
        beta[t] = transition @ (e[t+1] * beta[t+1]) / scale[t+1]
    return alpha, beta, scale, e


def fit_markov(sequences, max_iterations=25, tolerance=1e-7, pseudocount=0.5):
    if not sequences or pseudocount <= 0:
        raise ValueError("Markov EM needs sequences and positive smoothing")
    a = np.array([[0.9, 0.1], [0.1, 0.9]])
    pi = np.array([0.5, 0.5]); history = []
    for _ in range(max_iterations):
        counts = np.full((2, 2), pseudocount)
        initial = np.full(2, pseudocount); log_likelihood = 0.0
        for o in sequences:
            alpha, beta, c, e = forward_backward(o, a, pi)
            gamma0 = alpha[0] * beta[0]
            initial += gamma0 / gamma0.sum()
            # Vectorized transition counts; no full reference is an input.
            xi = (alpha[:-1, :, None] * a[None, :, :] *
                  (e[1:] * beta[1:])[:, None, :] / c[1:, None, None])
            counts += xi.sum(axis=0)
            log_likelihood += float(np.log(c).sum())
        new_a = counts / counts.sum(axis=1, keepdims=True)
        new_pi = initial / initial.sum()
        change = max(np.abs(new_a-a).max(), np.abs(new_pi-pi).max())
        a, pi = new_a, new_pi; history.append(log_likelihood)
        if change < tolerance:
            break
    return a, pi, history


def end_marginals(observed, transition, prior, k=3):
    alpha, beta, c, e = forward_backward(observed, transition, prior)
    q = np.zeros(len(observed))
    for t in range(k, len(q)):
        first = t-k
        value = alpha[first, 1]
        for j in range(first+1, t):
            value *= transition[1, 1] * e[j, 1] / c[j]
        value *= transition[1, 0] * e[t, 0] * beta[t, 0] / c[t]
        q[t] = value
    return np.clip(q, 0, 1)


def causal_forecast(observed, transition, prior, k=3):
    o = np.asarray(observed, dtype=np.int8)
    r = np.zeros(k+1); r[0] = 1; result = np.zeros(len(o))
    for t, obs in enumerate(o):
        result[t] = r[k] * transition[1, 0] if t else 0
        n = np.zeros_like(r)
        if t == 0:
            n[0], n[1] = prior
        else:
            n[0] = r[0]*transition[0, 0] + r[1:].sum()*transition[1, 0]
            n[1] = r[0]*transition[0, 1]
            for state in range(1, k+1):
                n[min(k, state+1)] += r[state]*transition[1, 1]
        n[0] *= obs != 1; n[1:] *= obs != 0
        if n.sum() <= 0:
            raise ValueError("Impossible causal evidence")
        r = n/n.sum()
    return result
