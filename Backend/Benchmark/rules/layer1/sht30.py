from __future__ import annotations

from typing import Any, Mapping, Sequence

try:
    from .config import (
        DEFAULT_WINDOW_HOURS,
        RULESET_VERSION,
        SHT30_FIELD_ALIASES,
        SHT30_SIGNAL_RULES,
    )
    from .reference import SignalRule, evaluate_signal_rules
except ImportError:
    from config import (
        DEFAULT_WINDOW_HOURS,
        RULESET_VERSION,
        SHT30_FIELD_ALIASES,
        SHT30_SIGNAL_RULES,
    )
    from reference import SignalRule, evaluate_signal_rules


def evaluate_sht30_sample(
    sample: Mapping[str, Any],
    history: Sequence[Mapping[str, Any]] | None = None,
    previous_signals: Mapping[str, Any] | None = None,
    rules: Sequence[SignalRule] = SHT30_SIGNAL_RULES,
) -> dict[str, Any]:
    return evaluate_signal_rules(
        source_object="sht30",
        sample=sample,
        history=history,
        previous_signals=previous_signals,
        rules=rules,
        aliases=SHT30_FIELD_ALIASES,
        window_hours=DEFAULT_WINDOW_HOURS,
        ruleset_version=RULESET_VERSION,
    )


def evaluate_sample(
    sample: Mapping[str, Any],
    history: Sequence[Mapping[str, Any]] | None = None,
    previous_signals: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return evaluate_sht30_sample(
        sample=sample,
        history=history,
        previous_signals=previous_signals,
    )
