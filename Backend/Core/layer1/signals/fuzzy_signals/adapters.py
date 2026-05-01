from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .config import RULESET_VERSION, SOURCE_CONFIGS
from .engine import SignalRule, evaluate_signal_rules


@dataclass(frozen=True)
class FuzzySignalAdapter:
    source_object: str
    aliases: Mapping[str, Sequence[str]]
    rules: Sequence[SignalRule]
    window_hours: Sequence[int]
    ruleset_version: str = RULESET_VERSION

    def evaluate(
        self,
        sample: Mapping[str, Any],
        history: Sequence[Mapping[str, Any]] | None = None,
        previous_signals: Mapping[str, Any] | None = None,
        rules: Sequence[SignalRule] | None = None,
    ) -> dict[str, Any]:
        return evaluate_signal_rules(
            source_object=self.source_object,
            sample=sample,
            history=history,
            previous_signals=previous_signals,
            rules=rules or self.rules,
            aliases=self.aliases,
            window_hours=self.window_hours,
            ruleset_version=self.ruleset_version,
        )


def build_adapter(source_object: str) -> FuzzySignalAdapter:
    if source_object not in SOURCE_CONFIGS:
        raise KeyError(f"Unknown fuzzy signal source: {source_object}")
    config = SOURCE_CONFIGS[source_object]
    return FuzzySignalAdapter(
        source_object=source_object,
        aliases=config["aliases"],
        rules=config["rules"],
        window_hours=config["window_hours"],
    )


ADAPTERS: dict[str, FuzzySignalAdapter] = {
    source_object: build_adapter(source_object)
    for source_object in SOURCE_CONFIGS
}


def evaluate_fuzzy_sample(
    source_object: str,
    sample: Mapping[str, Any],
    history: Sequence[Mapping[str, Any]] | None = None,
    previous_signals: Mapping[str, Any] | None = None,
    rules: Sequence[SignalRule] | None = None,
) -> dict[str, Any]:
    return ADAPTERS[source_object].evaluate(
        sample=sample,
        history=history,
        previous_signals=previous_signals,
        rules=rules,
    )
