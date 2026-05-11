from __future__ import annotations

from typing import Any, Mapping, Sequence

from .adapters import evaluate_fuzzy_sample
from .engine import SignalRule


def evaluate_sht30_sample(
    sample: Mapping[str, Any],
    history: Sequence[Mapping[str, Any]] | None = None,
    previous_signals: Mapping[str, Any] | None = None,
    rules: Sequence[SignalRule] | None = None,
) -> dict[str, Any]:
    return evaluate_fuzzy_sample(
        source_object="sht30",
        sample=sample,
        history=history,
        previous_signals=previous_signals,
        rules=rules,
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
