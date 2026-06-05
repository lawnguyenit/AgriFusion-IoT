from __future__ import annotations

from pathlib import Path

from Backend.Benchmark.shared.labels import (
    FOUR_CLASS_SCHEME,
    LEGACY_MOISTURE_OR_INTERVENTION_CONTEXT,
    RAIN_OR_FERTIGATION_CONTEXT,
    default_context_build_root,
    default_context_report_root,
    default_context_training_root,
    get_label_scheme,
    infer_label_scheme_from_context_labels,
    normalize_context_label_name,
)

CONTEXT_LABEL_ALIASES: dict[str, str] = {
    LEGACY_MOISTURE_OR_INTERVENTION_CONTEXT: RAIN_OR_FERTIGATION_CONTEXT,
}

LABEL_SCHEMES = {
    FOUR_CLASS_SCHEME.name: FOUR_CLASS_SCHEME,
    **{alias: FOUR_CLASS_SCHEME for alias in FOUR_CLASS_SCHEME.aliases},
}


def default_output_root(context_classifier_root: Path, label_scheme_name: str) -> Path:
    return default_context_build_root(context_classifier_root, label_scheme_name)


__all__ = [
    "CONTEXT_LABEL_ALIASES",
    "FOUR_CLASS_SCHEME",
    "LABEL_SCHEMES",
    "RAIN_OR_FERTIGATION_CONTEXT",
    "default_context_build_root",
    "default_context_report_root",
    "default_context_training_root",
    "default_output_root",
    "get_label_scheme",
    "infer_label_scheme_from_context_labels",
    "normalize_context_label_name",
]
