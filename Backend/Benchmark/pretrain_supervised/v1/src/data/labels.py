from __future__ import annotations

from pathlib import Path

import pandas as pd

from Backend.Benchmark.pretrain_supervised.v1.src.data.contracts import LabelPolicyResult


BINARY_CLASS_NAMES = ["normal", "abnormal"]
TERNARY_CLASS_NAMES = [
    "normal",
    "environmental_context",
    "operational_or_intervention",
]

ENVIRONMENTAL_CONTEXT_LABELS = {"weather_context", "stress_context"}
OPERATIONAL_CONTEXT_LABELS = {"system_timing", "sensor_fault_anomaly", "intervention_context"}

DEFAULT_LABEL_COLUMNS = [
    "timestamp",
    "event_source",
    "event_confidence",
    "event_reason",
    "event_primary",
    "event_labels",
    "big_label",
]


def load_event_label_frame(event_csv: Path) -> pd.DataFrame:
    frame = pd.read_csv(event_csv)
    frame["timestamp"] = pd.to_numeric(frame["timestamp"], errors="coerce")
    frame = frame.dropna(subset=["timestamp"]).copy()
    frame["timestamp"] = frame["timestamp"].astype("int64")
    frame = frame.sort_values("timestamp", kind="stable").drop_duplicates(subset=["timestamp"], keep="last")
    label_columns = [column for column in DEFAULT_LABEL_COLUMNS if column in frame.columns]
    return frame[label_columns].copy()


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

    def ternary_mapper(value: str) -> str:
        if value == "none":
            return "normal"
        if value in ENVIRONMENTAL_CONTEXT_LABELS:
            return "environmental_context"
        if value in OPERATIONAL_CONTEXT_LABELS:
            return "operational_or_intervention"
        return "operational_or_intervention"

    frame["ternary_label_name"] = source_series.apply(ternary_mapper)
    frame["ternary_label_id"] = frame["ternary_label_name"].map(
        {
            "normal": 0,
            "environmental_context": 1,
            "operational_or_intervention": 2,
        }
    ).astype(int)
    return frame


def _count_classes(frame: pd.DataFrame, class_names: list[str], label_column: str) -> dict[str, int]:
    counts = frame[label_column].value_counts(dropna=False)
    return {name: int(counts.get(name, 0)) for name in class_names}


def select_label_policy(
    dataframe: pd.DataFrame,
    requested_mode: str,
    min_class_support: int,
    min_class_ratio: float,
) -> LabelPolicyResult:
    train_frame = dataframe[dataframe["split"] == "train"].copy() if "split" in dataframe.columns else dataframe.copy()

    binary_counts = _count_classes(train_frame, BINARY_CLASS_NAMES, "binary_label_name")
    ternary_counts = _count_classes(train_frame, TERNARY_CLASS_NAMES, "ternary_label_name")
    ternary_supported = all(count >= min_class_support for count in ternary_counts.values())
    ternary_min = min(ternary_counts.values()) if ternary_counts else 0
    ternary_max = max(ternary_counts.values()) if ternary_counts else 0
    ternary_ratio_supported = ternary_max > 0 and (ternary_min / ternary_max) >= min_class_ratio
    ternary_ready = ternary_supported and ternary_ratio_supported

    if requested_mode == "binary":
        selected_mode = "binary"
    elif requested_mode == "ternary":
        if not ternary_ready:
            raise ValueError(
                "Requested ternary mode but train split does not have enough support and balance for ternary mode."
            )
        selected_mode = "ternary"
    else:
        selected_mode = "ternary" if ternary_ready else "binary"

    if selected_mode == "binary":
        class_names = BINARY_CLASS_NAMES
        label_column = "binary_label_name"
        label_id_column = "binary_label_id"
        class_to_id = {"normal": 0, "abnormal": 1}
        class_counts = binary_counts
    else:
        class_names = TERNARY_CLASS_NAMES
        label_column = "ternary_label_name"
        label_id_column = "ternary_label_id"
        class_to_id = {
            "normal": 0,
            "environmental_context": 1,
            "operational_or_intervention": 2,
        }
        class_counts = ternary_counts

    diagnostics = {
        "requested_mode": requested_mode,
        "binary_counts_train": binary_counts,
        "ternary_counts_train": ternary_counts,
        "ternary_supported": ternary_supported,
        "ternary_ratio_supported": ternary_ratio_supported,
        "ternary_ready": ternary_ready,
        "selected_train_rows": int(len(train_frame)),
    }
    return LabelPolicyResult(
        label_mode=selected_mode,
        label_column=label_column,
        label_id_column=label_id_column,
        class_names=class_names,
        class_to_id=class_to_id,
        class_counts=class_counts,
        diagnostics=diagnostics,
    )
