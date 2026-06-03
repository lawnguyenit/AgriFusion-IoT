from __future__ import annotations

import json
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import torch
from sklearn.exceptions import InconsistentVersionWarning

try:
    from Benchmark.context_classifier.src.data.tabular_builder import (
        build_v0_tabular,
        build_v1_tabular,
        build_v2_tabular,
        build_v3_tabular,
    )
    from Benchmark.ft_transformer_benchmark.src.model.ft_transformer_classifier import (
        FTTransformerClassifier,
        FTTransformerClassifierConfig,
    )
    from Benchmark.fuzzy_logic_basic.layer1.alignment import align_layer1_records
    from Benchmark.fuzzy_logic_basic.layer1.config import AlignmentConfig
except ModuleNotFoundError:
    from Backend.Benchmark.context_classifier.src.data.tabular_builder import (
        build_v0_tabular,
        build_v1_tabular,
        build_v2_tabular,
        build_v3_tabular,
    )
    from Backend.Benchmark.ft_transformer_benchmark.src.model.ft_transformer_classifier import (
        FTTransformerClassifier,
        FTTransformerClassifierConfig,
    )
    from Backend.Benchmark.fuzzy_logic_basic.layer1.alignment import align_layer1_records
    from Backend.Benchmark.fuzzy_logic_basic.layer1.config import AlignmentConfig

try:
    from Config.runtime import BackendSettings
except ModuleNotFoundError:
    from ...Config.runtime import BackendSettings


DISPLAY_LABELS = {
    "normal_context": "Binh thuong",
    "packet_loss_outage": "Packet loss outage",
    "water_deficit": "Thieu nuoc",
    "rain_or_fertigation_context": "Mua-am hoac tuoi-bon",
    "moisture_or_intervention_context": "Mua-am hoac tuoi-bon",
}

RUNTIME_METADATA_COLUMNS = {
    "timestamp",
    "context_label",
    "data_origin",
    "is_synthetic",
    "source_reference",
    "split_name",
}


@dataclass(frozen=True)
class ContextFTModelArtifact:
    aggregate_metrics_path: Path
    training_report_path: Path
    experiment_dir: Path
    experiment_name: str
    artifact_path: Path
    feature_schema_path: Path
    scaler_path: Path
    imputer_path: Path
    label_scheme: str
    class_names: tuple[str, ...]
    feature_names: tuple[str, ...]
    validation_macro_f1: float
    test_macro_f1: float
    window_sizes: tuple[int, ...]


def display_label_for_context(label: str) -> str:
    normalized = "rain_or_fertigation_context" if label == "moisture_or_intervention_context" else label
    return DISPLAY_LABELS.get(normalized, normalized.replace("_", " "))


def discover_best_ft_context_artifact(benchmark_root: Path) -> ContextFTModelArtifact | None:
    training_root = benchmark_root / "context_classifier" / "outputs_option2_4class" / "training"
    if not training_root.exists():
        return None

    best_candidate: ContextFTModelArtifact | None = None
    for aggregate_metrics_path in training_root.rglob("aggregate_model_metrics.csv"):
        training_dir = aggregate_metrics_path.parent
        training_report_path = training_dir / "training_report.json"
        if not training_report_path.exists():
            continue
        report_payload = _load_json(training_report_path)
        if str(report_payload.get("label_scheme", "")) != "option2_4class":
            continue

        build_manifest = report_payload.get("build_manifest", {})
        window_sizes = tuple(int(value) for value in build_manifest.get("window_sizes", [3, 8]))
        metrics_frame = pd.read_csv(aggregate_metrics_path)
        filtered = metrics_frame.loc[
            metrics_frame["model_name"].astype(str) == "ft_transformer_classifier"
        ].copy()
        if filtered.empty:
            continue

        for metric_row in filtered.to_dict(orient="records"):
            experiment_name = str(metric_row["experiment_name"])
            experiment_dir = training_dir / "experiments" / experiment_name
            feature_schema_path = experiment_dir / "feature_schema.json"
            scaler_path = experiment_dir / "scaler.pkl"
            imputer_path = experiment_dir / "imputer.pkl"
            artifact_path = Path(str(metric_row["artifact_path"]))
            if not (
                artifact_path.exists()
                and feature_schema_path.exists()
                and scaler_path.exists()
                and imputer_path.exists()
            ):
                continue

            feature_schema = _load_json(feature_schema_path)
            class_names = tuple(
                str(name)
                for name in (
                    feature_schema.get("class_names")
                    or build_manifest.get("class_names")
                    or []
                )
            )
            feature_names = tuple(str(name) for name in feature_schema.get("feature_names", []))
            candidate = ContextFTModelArtifact(
                aggregate_metrics_path=aggregate_metrics_path,
                training_report_path=training_report_path,
                experiment_dir=experiment_dir,
                experiment_name=experiment_name,
                artifact_path=artifact_path,
                feature_schema_path=feature_schema_path,
                scaler_path=scaler_path,
                imputer_path=imputer_path,
                label_scheme="option2_4class",
                class_names=class_names,
                feature_names=feature_names,
                validation_macro_f1=float(metric_row["validation_macro_f1"]),
                test_macro_f1=float(metric_row["test_macro_f1"]),
                window_sizes=window_sizes,
            )
            if best_candidate is None:
                best_candidate = candidate
                continue
            if (
                candidate.test_macro_f1,
                candidate.validation_macro_f1,
                _experiment_priority(candidate.experiment_name),
            ) > (
                best_candidate.test_macro_f1,
                best_candidate.validation_macro_f1,
                _experiment_priority(best_candidate.experiment_name),
            ):
                best_candidate = candidate
    return best_candidate


class ContextFTRuntimeDiagnosisModel:
    def __init__(self, artifact: ContextFTModelArtifact):
        self.artifact = artifact
        checkpoint = torch.load(artifact.artifact_path, map_location="cpu", weights_only=True)
        config = FTTransformerClassifierConfig(**checkpoint["config"])
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = FTTransformerClassifier(
            input_dim=int(checkpoint["input_dim"]),
            output_dim=int(checkpoint["output_dim"]),
            config=config,
        ).to(self.device)
        self.model.load_state_dict(checkpoint["state_dict"])
        self.model.eval()
        self.feature_names = list(artifact.feature_names)
        self.class_names = list(artifact.class_names)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", InconsistentVersionWarning)
            self.imputer = joblib.load(artifact.imputer_path)
            self.scaler = joblib.load(artifact.scaler_path)

    def predict(self, feature_row: dict[str, float | int | None]) -> dict[str, Any]:
        frame = pd.DataFrame([{name: feature_row.get(name) for name in self.feature_names}])
        matrix = frame.to_numpy(dtype=np.float32)
        matrix = self.imputer.transform(matrix)
        matrix = self.scaler.transform(matrix)
        tensor = torch.tensor(matrix, dtype=torch.float32, device=self.device)
        with torch.no_grad():
            logits, diagnostics = self.model(tensor)
            probabilities = torch.softmax(logits, dim=1).detach().cpu().numpy()[0]
            class_id = int(np.argmax(probabilities))
        probability_map = {
            class_name: float(probabilities[index])
            for index, class_name in enumerate(self.class_names)
        }
        predicted_label = self.class_names[class_id]
        return {
            "label": predicted_label,
            "displayLabel": display_label_for_context(predicted_label),
            "labelId": class_id,
            "probabilities": probability_map,
            "abnormalProbability": float(1.0 - probability_map.get("normal_context", 0.0)),
            "diagnostics": diagnostics,
        }


def build_runtime_feature_row(settings: BackendSettings, artifact: ContextFTModelArtifact) -> dict[str, Any] | None:
    alignment_result = align_layer1_records(AlignmentConfig(input_root=settings.layer1_root))
    if isinstance(alignment_result, tuple):
        aligned_rows = alignment_result[0]
    else:
        aligned_rows = alignment_result
    if not aligned_rows:
        return None

    canonical_df = pd.DataFrame(aligned_rows).sort_values("timestamp").reset_index(drop=True)
    canonical_df["context_label"] = "normal_context"
    canonical_df["data_origin"] = "runtime"
    canonical_df["is_synthetic"] = 0
    canonical_df["source_reference"] = "layer1_runtime"
    canonical_df["split_name"] = "runtime"

    _inject_packet_loss_runtime_features(canonical_df)
    feature_df = _select_runtime_feature_frame(
        canonical_df=canonical_df,
        feature_names=artifact.feature_names,
        experiment_name=artifact.experiment_name,
    )

    if feature_df.empty:
        return None

    latest_row = feature_df.sort_values("timestamp").iloc[-1].to_dict()
    runtime_row = {name: latest_row.get(name) for name in artifact.feature_names}
    runtime_row["timestamp"] = int(latest_row["timestamp"])
    return runtime_row


def _inject_packet_loss_runtime_features(frame: pd.DataFrame) -> None:
    frame["loss_packet_count"] = 0
    frame["outage_duration_steps"] = 0
    frame["time_since_last_valid_step"] = 0
    frame["recovery_step_index"] = 0
    frame["nighttime_outage_flag"] = 0
    frame["sunrise_recovery_flag"] = 0

    if frame.empty:
        return

    timestamps = pd.to_numeric(frame["timestamp"], errors="coerce").astype("Int64")
    deltas = timestamps.diff().fillna(0).astype("Int64")
    regular_candidates = deltas[deltas.between(600, 1800)]
    expected_interval_sec = int(regular_candidates.median()) if not regular_candidates.empty else 900
    expected_interval_sec = max(expected_interval_sec, 900)

    local_times = pd.to_datetime(frame["timestamp"], unit="s", utc=True).dt.tz_convert("Asia/Ho_Chi_Minh")
    prev_times = local_times.shift(1)

    for index in range(1, len(frame)):
        gap_sec = int(deltas.iloc[index]) if pd.notna(deltas.iloc[index]) else 0
        if gap_sec <= int(expected_interval_sec * 1.5):
            continue
        loss_steps = max(int(round(gap_sec / expected_interval_sec)) - 1, 1)
        frame.at[index, "loss_packet_count"] = loss_steps
        frame.at[index, "outage_duration_steps"] = loss_steps
        frame.at[index, "time_since_last_valid_step"] = loss_steps
        frame.at[index, "recovery_step_index"] = 1

        previous_time = prev_times.iloc[index]
        current_time = local_times.iloc[index]
        if previous_time is not pd.NaT and current_time is not pd.NaT:
            night_overlap = int(
                (previous_time.hour >= 18 or previous_time.hour <= 5)
                or (current_time.hour >= 18 or current_time.hour <= 5)
            )
            sunrise_recovery = int(
                (current_time.hour >= 6 and current_time.hour <= 9)
                and (previous_time.hour <= 5 or previous_time.hour >= 18)
            )
            frame.at[index, "nighttime_outage_flag"] = night_overlap
            frame.at[index, "sunrise_recovery_flag"] = sunrise_recovery


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _experiment_priority(experiment_name: str) -> int:
    priority = {
        "base": 0,
        "v0": 0,
        "v1": 1,
        "window": 2,
        "v2": 2,
        "combo": 3,
        "v3": 3,
    }
    return priority.get(str(experiment_name), -1)


def _select_runtime_feature_frame(
    *,
    canonical_df: pd.DataFrame,
    feature_names: tuple[str, ...],
    experiment_name: str,
) -> pd.DataFrame:
    candidates = {
        "v0": build_v0_tabular(canonical_df),
        "v1": build_v1_tabular(canonical_df),
        "v2": build_v2_tabular(canonical_df),
        "v3": build_v3_tabular(canonical_df),
    }
    required = list(feature_names)
    matching: list[tuple[int, int, str, pd.DataFrame]] = []

    for candidate_name, frame in candidates.items():
        candidate_columns = set(frame.columns)
        if not all(name in candidate_columns for name in required):
            continue
        model_feature_count = len([name for name in frame.columns if name not in RUNTIME_METADATA_COLUMNS])
        matching.append((model_feature_count, -_experiment_priority(candidate_name), candidate_name, frame))

    if matching:
        matching.sort(key=lambda item: (item[0], item[1], item[2]))
        return matching[0][3]

    raise ValueError(
        "No runtime tabular builder matches FT artifact "
        f"experiment={experiment_name} with features={required}"
    )
