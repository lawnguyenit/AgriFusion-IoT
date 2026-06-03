from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch
from sklearn.preprocessing import StandardScaler

from Backend.Benchmark.pretrain_supervised.pretrain.src.config.settings import PretrainConfig
from Backend.Benchmark.pretrain_supervised.pretrain.src.data.preprocessing import prepare_pretraining_dataframe
from Backend.Benchmark.pretrain_supervised.pretrain.src.model.tabnet_pretrainer import TabNetPretrainingModel
from Backend.Benchmark.pretrain_supervised.v0.src.config.settings import V0Config
from Backend.Benchmark.pretrain_supervised.v0.src.data.checkpoints import discover_latest_checkpoint_for_experiment
from Backend.Benchmark.pretrain_supervised.v0.src.data.contracts import ExperimentEmbeddingBundle


def build_experiment_embedding_bundle(
    config: V0Config,
    *,
    experiment_name: str,
) -> ExperimentEmbeddingBundle:
    experiment_checkpoint = discover_latest_checkpoint_for_experiment(
        experiment_name=experiment_name,
        benchmark_version=config.benchmark_version,
        search_roots=config.pretrain_output_roots,
    )
    payload = _load_checkpoint_payload(experiment_checkpoint.checkpoint_path)
    pretrain_config = _rebuild_pretrain_config(dict(payload["config"]))
    prepared = prepare_pretraining_dataframe(pretrain_config)
    scaler = _load_scaler(experiment_checkpoint.checkpoint_path)

    feature_columns = list(prepared.feature_columns)
    scaled_features = scaler.transform(prepared.dataframe[feature_columns])
    feature_tensor = torch.tensor(scaled_features, dtype=torch.float32)

    model = TabNetPretrainingModel(input_dim=int(payload["input_dim"]), config=pretrain_config)
    model.load_state_dict(payload["state_dict"])
    model.eval()

    with torch.no_grad():
        embeddings, diagnostics = model.encode(feature_tensor)

    embedding_array = embeddings.cpu().numpy()
    embedding_columns = [f"embedding_{index}" for index in range(embedding_array.shape[1])]
    dataframe = prepared.dataframe.copy()
    for index, column in enumerate(embedding_columns):
        dataframe[column] = embedding_array[:, index]
    dataframe["embedding_attention_entropy"] = diagnostics["attention_entropy"]
    dataframe["embedding_mask_density"] = diagnostics["mask_density"]

    label_frame = _load_label_frame(config.event_csv)
    label_columns = [column for column in label_frame.columns if column not in dataframe.columns or column == "timestamp"]
    merged = dataframe.merge(label_frame[label_columns], on="timestamp", how="left", validate="one_to_one")
    label_merge_report = {
        "event_csv": str(config.event_csv),
        "labeled_rows": int(merged["big_label"].notna().sum()) if "big_label" in merged.columns else 0,
        "unlabeled_rows": int(merged["big_label"].isna().sum()) if "big_label" in merged.columns else int(len(merged)),
        "merge_columns": label_columns,
    }

    if "big_label" in merged.columns:
        merged["big_label"] = merged["big_label"].fillna("none")
    if "event_primary" in merged.columns:
        merged["event_primary"] = merged["event_primary"].fillna("none")

    return ExperimentEmbeddingBundle(
        experiment_name=experiment_name,
        source_kind=experiment_checkpoint.source_kind,
        dataframe=merged,
        feature_columns=feature_columns,
        embedding_columns=embedding_columns,
        embeddings=embedding_array,
        checkpoint_path=experiment_checkpoint.checkpoint_path,
        checkpoint_config=dict(payload["config"]),
        split_counts=prepared.split_counts,
        split_slices=prepared.split_slices,
        split_manifest=prepared.split_manifest,
        embedding_dim=int(embedding_array.shape[1]),
        label_merge_report=label_merge_report,
    )


def _load_checkpoint_payload(checkpoint_path: Path) -> dict[str, object]:
    try:
        payload = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    except TypeError:
        payload = torch.load(checkpoint_path, map_location="cpu")
    if not isinstance(payload, dict) or "config" not in payload or "input_dim" not in payload:
        raise ValueError(f"Invalid checkpoint payload: {checkpoint_path}")
    return payload


def _rebuild_pretrain_config(payload_config: dict[str, object]) -> PretrainConfig:
    config = PretrainConfig()
    for key, value in payload_config.items():
        if key in {"input_csv", "output_root"}:
            continue
        if hasattr(config, key):
            setattr(config, key, value)
    config.input_csv = Path(payload_config["input_csv"]).resolve()
    return config


def _load_scaler(checkpoint_path: Path) -> StandardScaler:
    scaler_stats_path = checkpoint_path.parent / "scaler_stats.json"
    if scaler_stats_path.exists():
        with scaler_stats_path.open("r", encoding="utf-8") as handle:
            stats = json.load(handle)
        scaler = StandardScaler()
        scaler.mean_ = np.asarray(stats["mean"], dtype=float)
        scaler.scale_ = np.asarray(stats["scale"], dtype=float)
        scaler.var_ = np.asarray(stats["var"], dtype=float)
        scaler.n_features_in_ = int(stats["n_features_in"])
        scaler.n_samples_seen_ = int(stats["n_samples_seen"])
        scaler.feature_names_in_ = np.asarray(stats["feature_columns"], dtype=object)
        return scaler

    scaler_path = checkpoint_path.parent / "scaler.pkl"
    if not scaler_path.exists():
        raise FileNotFoundError(f"Scaler not found next to checkpoint: {scaler_path}")
    return joblib.load(scaler_path)


def _load_label_frame(event_csv: Path) -> pd.DataFrame:
    frame = pd.read_csv(event_csv)
    frame["timestamp"] = pd.to_numeric(frame["timestamp"], errors="coerce")
    frame = frame.dropna(subset=["timestamp"]).copy()
    frame["timestamp"] = frame["timestamp"].astype("int64")
    frame = frame.sort_values("timestamp", kind="stable").drop_duplicates(subset=["timestamp"], keep="last")
    return frame

