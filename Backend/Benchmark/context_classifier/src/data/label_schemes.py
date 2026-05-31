from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LabelScheme:
    name: str
    class_names: tuple[str, ...]
    real_label_map: dict[str, str]
    synthetic_label_map: dict[str, str]
    output_folder_name: str
    description: str


FIVE_CLASS_V1 = LabelScheme(
    name="five_class_v1",
    class_names=(
        "normal_context",
        "packet_loss_outage",
        "rain_humid_context",
        "fertigation_spike",
        "water_deficit",
    ),
    real_label_map={
        "none": "normal_context",
        "weather_context": "rain_humid_context",
        "intervention_context": "fertigation_spike",
        "stress_context": "water_deficit",
        "system_timing": "packet_loss_outage",
        "sensor_fault_anomaly": "packet_loss_outage",
    },
    synthetic_label_map={
        "packet_loss": "packet_loss_outage",
    },
    output_folder_name="outputs",
    description="Original 5-class benchmark with separate rain and fertigation contexts.",
)


OPTION2_4CLASS = LabelScheme(
    name="option2_4class",
    class_names=(
        "normal_context",
        "packet_loss_outage",
        "water_deficit",
        "moisture_or_intervention_context",
    ),
    real_label_map={
        "none": "normal_context",
        "weather_context": "moisture_or_intervention_context",
        "intervention_context": "moisture_or_intervention_context",
        "stress_context": "water_deficit",
        "system_timing": "packet_loss_outage",
        "sensor_fault_anomaly": "packet_loss_outage",
    },
    synthetic_label_map={
        "packet_loss": "packet_loss_outage",
        "rain_humid_context": "moisture_or_intervention_context",
        "fertigation_spike": "moisture_or_intervention_context",
    },
    output_folder_name="outputs_option2_4class",
    description="Option 2 practical 4-class benchmark that merges rain and fertigation into one context.",
)


LABEL_SCHEMES: dict[str, LabelScheme] = {
    FIVE_CLASS_V1.name: FIVE_CLASS_V1,
    OPTION2_4CLASS.name: OPTION2_4CLASS,
}


def get_label_scheme(name: str) -> LabelScheme:
    try:
        return LABEL_SCHEMES[name]
    except KeyError as exc:
        available = ", ".join(sorted(LABEL_SCHEMES))
        raise ValueError(f"Unsupported label scheme: {name}. Available: {available}") from exc


def default_output_root(context_classifier_root: Path, label_scheme_name: str) -> Path:
    scheme = get_label_scheme(label_scheme_name)
    return (context_classifier_root / scheme.output_folder_name).resolve()


def infer_label_scheme_from_context_labels(context_labels: list[str] | set[str]) -> LabelScheme | None:
    labels = {str(label) for label in context_labels if str(label)}
    if not labels:
        return None
    for scheme in LABEL_SCHEMES.values():
        if labels.issubset(set(scheme.class_names)):
            return scheme
    return None
