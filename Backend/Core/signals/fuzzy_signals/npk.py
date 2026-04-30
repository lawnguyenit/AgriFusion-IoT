from __future__ import annotations

from typing import Any, Mapping, Sequence

try:
    from .config import (
        DEFAULT_WINDOW_HOURS,
        NPK_FIELD_ALIASES,
        NPK_SIGNAL_RULES,
        RULESET_VERSION,
    )
    from .reference import SignalRule, evaluate_signal_rules
except ImportError:
    from config import (
        DEFAULT_WINDOW_HOURS,
        NPK_FIELD_ALIASES,
        NPK_SIGNAL_RULES,
        RULESET_VERSION,
    )
    from reference import SignalRule, evaluate_signal_rules


def evaluate_npk_sample(
    sample: Mapping[str, Any],
    history: Sequence[Mapping[str, Any]] | None = None,
    previous_signals: Mapping[str, Any] | None = None,
    rules: Sequence[SignalRule] = NPK_SIGNAL_RULES,
) -> dict[str, Any]:
    """Evaluate one NPK sample into fuzzy layer-1 signals.

    `sample` can be raw (`{"N": 100, "P": 100, "K": 55}`) or canonical
    (`{"n_ppm": 100, "p_ppm": 100, "k_ppm": 55}`).
    """
    return evaluate_signal_rules(
        source_object="npk",
        sample=sample,
        history=history,
        previous_signals=previous_signals,
        rules=rules,
        aliases=NPK_FIELD_ALIASES,
        window_hours=DEFAULT_WINDOW_HOURS,
        ruleset_version=RULESET_VERSION,
    )


def evaluate_sample(
    sample: Mapping[str, Any],
    history: Sequence[Mapping[str, Any]] | None = None,
    previous_signals: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return evaluate_npk_sample(
        sample=sample,
        history=history,
        previous_signals=previous_signals,
    )
