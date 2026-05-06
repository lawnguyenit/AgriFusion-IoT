from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class ECConsistencyModel:
    slope: float
    intercept: float
    sample_count: int
    r2: float | None = None


def fit_ec_model(
    samples: Iterable[dict[str, float | int | None]],
    default_slope: float,
    default_intercept: float,
    min_samples: int = 2,
) -> ECConsistencyModel:
    xs: list[float] = []
    ys: list[float] = []
    for sample in samples:
        ec = sample.get("EC")
        n = sample.get("N")
        p = sample.get("P")
        k = sample.get("K")
        if ec is None or n is None or p is None or k is None:
            continue
        x = float(n) + float(p) + float(k)
        y = float(ec)
        xs.append(x)
        ys.append(y)

    if len(xs) < max(2, min_samples):
        return ECConsistencyModel(
            slope=default_slope,
            intercept=default_intercept,
            sample_count=len(xs),
            r2=None,
        )

    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    var_x = sum((x - mean_x) ** 2 for x in xs)
    if var_x <= 1e-9:
        return ECConsistencyModel(
            slope=default_slope,
            intercept=default_intercept,
            sample_count=len(xs),
            r2=None,
        )

    cov_xy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=False))
    slope = cov_xy / var_x
    intercept = mean_y - slope * mean_x

    ss_tot = sum((y - mean_y) ** 2 for y in ys)
    ss_res = sum((y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys, strict=False))
    r2 = None if ss_tot <= 1e-9 else max(0.0, 1.0 - (ss_res / ss_tot))
    return ECConsistencyModel(slope=slope, intercept=intercept, sample_count=len(xs), r2=r2)


def _score_from_ratio(ratio: float, warn_ratio: float, critical_ratio: float) -> float:
    if ratio <= warn_ratio:
        return max(0.0, 1.0 - (ratio / max(warn_ratio, 1e-9)) * 0.15)
    if ratio <= critical_ratio:
        span = max(critical_ratio - warn_ratio, 1e-9)
        return max(0.0, 0.85 - ((ratio - warn_ratio) / span) * 0.55)
    return max(0.0, 0.30 - min(0.30, (ratio - critical_ratio) * 0.9))


def check_ec_npk_consistency(
    ec: float | None,
    n: float | None,
    p: float | None,
    k: float | None,
    *,
    model: ECConsistencyModel,
    warn_ratio: float,
    critical_ratio: float,
) -> tuple[float, str, str]:
    if ec is None:
        return 0.0, "missing_ec", "EC missing, cannot evaluate EC-NPK consistency"
    if n is None or p is None or k is None:
        return 0.0, "missing_npk", "NPK missing, cannot evaluate EC-NPK consistency"

    n_sum = float(n) + float(p) + float(k)
    expected = model.intercept + model.slope * n_sum
    if expected <= 0:
        return 0.0, "invalid_model", "EC model not calibrated"

    ratio = abs(float(ec) - expected) / expected
    if ratio <= warn_ratio:
        score = _score_from_ratio(ratio, warn_ratio, critical_ratio)
        return round(score, 4), "ok", f"EC matches NPK-derived expectation within {ratio:.3f} residual ratio"
    if ratio <= critical_ratio:
        score = _score_from_ratio(ratio, warn_ratio, critical_ratio)
        return round(score, 4), "watch", f"EC deviates moderately from NPK-derived expectation (ratio={ratio:.3f})"

    score = _score_from_ratio(ratio, warn_ratio, critical_ratio)
    return round(score, 4), "warning", f"EC deviates strongly from NPK-derived expectation (ratio={ratio:.3f})"
