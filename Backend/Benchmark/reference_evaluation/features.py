"""Causal features receive visible values only, never full audit reference."""
import numpy as np


def causal_features(visible_values, history, median, scale, age_cap=70):
    x = np.asarray(visible_values, dtype=float)
    if history < 1 or not np.isfinite([median, scale]).all() or scale <= 0:
        raise ValueError("Invalid feature configuration")
    result = np.empty((len(x), 2*history+1))
    filled = [float(median)]*history
    flags = [1.0]*history; last = float(median); age = float(age_cap)
    for t, value in enumerate(x):
        result[t, :history] = (np.asarray(filled[-history:])-median)/scale
        result[t, history:2*history] = flags[-history:]
        result[t, -1] = min(age, age_cap)/age_cap
        missing = not np.isfinite(value)
        if not missing:
            last = value; age = 0
        else:
            age += 1
        filled.append(last); flags.append(float(missing))
        # Keep bounded history rather than quadratic full-series slicing.
        if len(filled) > 2*history:
            filled = filled[-history:]; flags = flags[-history:]
    return result
