from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from Backend.Benchmark.shared.contracts import LabelPolicyResult

RAIN_OR_FERTIGATION_CONTEXT = "rain_or_fertigation_context"
LEGACY_MOISTURE_OR_INTERVENTION_CONTEXT = "moisture_or_intervention_context"
CONTEXT_LABEL_ALIASES: dict[str, str] = {
    LEGACY_MOISTURE_OR_INTERVENTION_CONTEXT: RAIN_OR_FERTIGATION_CONTEXT,
}

BINARY_LABELS = ("normal", "abnormal")
TRI_CLASS_LABELS = ("normal", "system_context", "field_context")
FOUR_CLASS_CONTEXT = (
    "normal_context",
    "packet_loss_outage",
    "water_deficit",
    RAIN_OR_FERTIGATION_CONTEXT,
)

DEFAULT_EVENT_LABEL_COLUMNS = [
    "timestamp",
    "event_source",
    "event_confidence",
    "event_reason",
    "event_primary",
    "event_labels",
    "big_label",
]


@dataclass(frozen=True)
class LabelScheme:
    name: str
    aliases: tuple[str, ...]
    class_names: tuple[str, ...]
    real_label_map: dict[str, str]
    synthetic_label_map: dict[str, str]
    build_root_name: str
    description: str


TRI_CLASS_CONTEXT_LABELS = {
    "system_timing": "system_context",
    "sensor_fault_anomaly": "system_context",
    "intervention_context": "system_context",
    "weather_context": "field_context",
    "stress_context": "field_context",
}

FOUR_CLASS_SCHEME = LabelScheme(
    name="four_class",
    aliases=("option2_4class",),
    class_names=FOUR_CLASS_CONTEXT,
    real_label_map={
        "none": "normal_context",
        "weather_context": RAIN_OR_FERTIGATION_CONTEXT,
        "intervention_context": RAIN_OR_FERTIGATION_CONTEXT,
        "stress_context": "water_deficit",
        "system_timing": "packet_loss_outage",
        "sensor_fault_anomaly": "packet_loss_outage",
    },
    synthetic_label_map={
        "packet_loss": "packet_loss_outage",
        "rain_humid_context": RAIN_OR_FERTIGATION_CONTEXT,
        "fertigation_spike": RAIN_OR_FERTIGATION_CONTEXT,
        RAIN_OR_FERTIGATION_CONTEXT: RAIN_OR_FERTIGATION_CONTEXT,
        LEGACY_MOISTURE_OR_INTERVENTION_CONTEXT: RAIN_OR_FERTIGATION_CONTEXT,
        "normal_context": "normal_context",
        "packet_loss_outage": "packet_loss_outage",
        "water_deficit": "water_deficit",
    },
    build_root_name="four_class",
    description="Canonical 4-class context benchmark based on the former option2_4class contract.",
)

LABEL_SCHEMES: dict[str, LabelScheme] = {
    FOUR_CLASS_SCHEME.name: FOUR_CLASS_SCHEME,
    **{alias: FOUR_CLASS_SCHEME for alias in FOUR_CLASS_SCHEME.aliases},
}


def get_label_scheme(name: str) -> LabelScheme:
    normalized = str(name).strip()
    try:
        return LABEL_SCHEMES[normalized]
    except KeyError as exc:
        available = ", ".join(sorted({scheme.name for scheme in LABEL_SCHEMES.values()}))
        raise ValueError(f"Unsupported label scheme: {name}. Available: {available}") from exc


def default_context_build_root(context_benchmark_root: Path, label_scheme_name: str, variant: str = "augmented") -> Path:
    scheme = get_label_scheme(label_scheme_name)
    return (context_benchmark_root / "artifacts" / "builds" / scheme.build_root_name / variant).resolve()


def default_context_training_root(context_benchmark_root: Path, label_scheme_name: str) -> Path:
    scheme = get_label_scheme(label_scheme_name)
    return (context_benchmark_root / "artifacts" / "training" / scheme.build_root_name).resolve()


def default_context_report_root(context_benchmark_root: Path, label_scheme_name: str) -> Path:
    scheme = get_label_scheme(label_scheme_name)
    return (context_benchmark_root / "artifacts" / "reports" / scheme.build_root_name).resolve()


def normalize_context_label_name(label: str) -> str:
    normalized = str(label).strip()
    return CONTEXT_LABEL_ALIASES.get(normalized, normalized)


def infer_label_scheme_from_context_labels(context_labels: list[str] | set[str]) -> LabelScheme | None:
    labels = {normalize_context_label_name(str(label)) for label in context_labels if str(label)}
    if not labels:
        return None
    if labels.issubset({normalize_context_label_name(name) for name in FOUR_CLASS_SCHEME.class_names}):
        return FOUR_CLASS_SCHEME
    return None


def load_event_label_frame(event_csv: Path) -> pd.DataFrame:
    frame = pd.read_csv(event_csv)
    frame["timestamp"] = pd.to_numeric(frame["timestamp"], errors="coerce")
    frame = frame.dropna(subset=["timestamp"]).copy()
    frame["timestamp"] = frame["timestamp"].astype("int64")
    frame = frame.sort_values("timestamp", kind="stable").drop_duplicates(subset=["timestamp"], keep="last")
    columns = [column for column in DEFAULT_EVENT_LABEL_COLUMNS if column in frame.columns]
    return frame[columns].copy()


def merge_event_labels(dataframe: pd.DataFrame, event_csv: Path) -> tuple[pd.DataFrame, dict[str, object]]:
    label_frame = load_event_label_frame(event_csv)
    label_columns = [
        column
        for column in label_frame.columns
        if column != "timestamp" and column not in dataframe.columns
    ]
    if not label_columns:
        report = {
            "event_csv": str(event_csv),
            "labeled_rows": int(dataframe["big_label"].notna().sum()) if "big_label" in dataframe.columns else 0,
            "unlabeled_rows": int(dataframe["big_label"].isna().sum()) if "big_label" in dataframe.columns else int(len(dataframe)),
            "merge_columns": ["timestamp"],
            "notes": ["All available label columns were already present in the source dataframe."],
        }
        return dataframe.copy(), report
    merged = dataframe.merge(label_frame[["timestamp", *label_columns]], on="timestamp", how="left", validate="one_to_one")
    report = {
        "event_csv": str(event_csv),
        "labeled_rows": int(merged["big_label"].notna().sum()) if "big_label" in merged.columns else 0,
        "unlabeled_rows": int(merged["big_label"].isna().sum()) if "big_label" in merged.columns else int(len(merged)),
        "merge_columns": ["timestamp", *label_columns],
    }
    return merged, report


def build_label_frame(dataframe: pd.DataFrame) -> pd.DataFrame:
    frame = dataframe.copy()
    source_series = frame.get("big_label")
    if source_series is None:
        source_series = frame.get("event_primary")
    if source_series is None:
        source_series = pd.Series(["none"] * len(frame), index=frame.index)
    source_series = source_series.fillna("none").astype(str)

    frame["label_source"] = source_series
    frame["binary_label_name"] = source_series.apply(lambda value: "normal" if value == "none" else "abnormal")
    frame["binary_label_id"] = frame["binary_label_name"].map({"normal": 0, "abnormal": 1}).astype(int)

    def tri_class_mapper(value: str) -> str:
        if value == "none":
            return "normal"
        return TRI_CLASS_CONTEXT_LABELS.get(value, "system_context")

    frame["tri_class_label_name"] = source_series.apply(tri_class_mapper)
    frame["tri_class_label_id"] = frame["tri_class_label_name"].map(
        {
            "normal": 0,
            "system_context": 1,
            "field_context": 2,
        }
    ).astype(int)

    frame["four_class_label_name"] = source_series.map(FOUR_CLASS_SCHEME.real_label_map).fillna("normal_context")
    frame["four_class_label_id"] = frame["four_class_label_name"].map(
        {name: index for index, name in enumerate(FOUR_CLASS_SCHEME.class_names)}
    ).astype(int)
    return frame


def select_label_policy(
    dataframe: pd.DataFrame,
    requested_mode: str,
    min_class_support: int,
    min_class_ratio: float,
    *,
    enforce_balance_for_explicit: bool = True,
) -> LabelPolicyResult:
    train_frame = dataframe[dataframe["split"] == "train"].copy() if "split" in dataframe.columns else dataframe.copy()

    binary_counts = _count_classes(train_frame, list(BINARY_LABELS), "binary_label_name")
    tri_counts = _count_classes(train_frame, list(TRI_CLASS_LABELS), "tri_class_label_name")
    four_counts = _count_classes(train_frame, list(FOUR_CLASS_SCHEME.class_names), "four_class_label_name")

    tri_ready = _is_supported(tri_counts, min_class_support=min_class_support, min_class_ratio=min_class_ratio)
    four_ready = _is_supported(four_counts, min_class_support=min_class_support, min_class_ratio=min_class_ratio)

    if requested_mode == "binary":
        return _label_policy_from_mode("binary", binary_counts)
    if requested_mode == "tri_class":
        if enforce_balance_for_explicit and not tri_ready:
            raise ValueError("Requested tri_class mode but train split does not have enough support and balance.")
        return _label_policy_from_mode(
            "tri_class",
            tri_counts,
            binary_counts=binary_counts,
            four_counts=four_counts,
        )
    if requested_mode == "four_class":
        if enforce_balance_for_explicit and not four_ready:
            raise ValueError("Requested four_class mode but train split does not have enough support and balance.")
        return _label_policy_from_mode(
            "four_class",
            four_counts,
            binary_counts=binary_counts,
            tri_counts=tri_counts,
        )
    if requested_mode != "auto":
        raise ValueError(f"Unsupported label_mode: {requested_mode}")

    if tri_ready:
        return _label_policy_from_mode("tri_class", tri_counts, binary_counts=binary_counts, four_counts=four_counts)
    return _label_policy_from_mode("binary", binary_counts, tri_counts=tri_counts, four_counts=four_counts)


def _label_policy_from_mode(
    mode: str,
    class_counts: dict[str, int],
    *,
    binary_counts: dict[str, int] | None = None,
    tri_counts: dict[str, int] | None = None,
    four_counts: dict[str, int] | None = None,
) -> LabelPolicyResult:
    if mode == "binary":
        class_names = list(BINARY_LABELS)
        label_column = "binary_label_name"
        label_id_column = "binary_label_id"
    elif mode == "tri_class":
        class_names = list(TRI_CLASS_LABELS)
        label_column = "tri_class_label_name"
        label_id_column = "tri_class_label_id"
    elif mode == "four_class":
        class_names = list(FOUR_CLASS_SCHEME.class_names)
        label_column = "four_class_label_name"
        label_id_column = "four_class_label_id"
    else:
        raise ValueError(f"Unsupported label policy mode: {mode}")

    class_to_id = {name: index for index, name in enumerate(class_names)}
    diagnostics = {
        "requested_mode": mode,
        "binary_counts_train": binary_counts or {},
        "tri_class_counts_train": tri_counts or {},
        "four_class_counts_train": four_counts or {},
        "selected_mode": mode,
    }
    return LabelPolicyResult(
        label_mode=mode,
        label_column=label_column,
        label_id_column=label_id_column,
        class_names=class_names,
        class_to_id=class_to_id,
        class_counts=class_counts,
        diagnostics=diagnostics,
    )


def _count_classes(frame: pd.DataFrame, class_names: list[str], label_column: str) -> dict[str, int]:
    counts = frame[label_column].value_counts(dropna=False)
    return {name: int(counts.get(name, 0)) for name in class_names}


def _is_supported(class_counts: dict[str, int], *, min_class_support: int, min_class_ratio: float) -> bool:
    if not class_counts:
        return False
    values = list(class_counts.values())
    if any(count < min_class_support for count in values):
        return False
    majority = max(values)
    minority = min(values)
    return majority > 0 and (minority / majority) >= min_class_ratio
