from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch
from sklearn.preprocessing import StandardScaler

from Backend.Benchmark.pretrain_supervised.v1.src.config.settings import (
    DEFAULT_PRETRAIN_OUTPUT_ROOTS,
    V1Config,
)
from Backend.Benchmark.pretrain_supervised.v1.src.data.contracts import EmbeddingBundle
from Backend.Benchmark.pretrain_supervised.pretrain.src.config.settings import PretrainConfig
from Backend.Benchmark.pretrain_supervised.pretrain.src.data.preprocessing import prepare_pretraining_dataframe
from Backend.Benchmark.pretrain_supervised.pretrain.src.model.tabnet_pretrainer import TabNetPretrainingModel


def discover_latest_checkpoint(search_roots: list[Path] | None = None) -> Path:
    candidates: list[Path] = []
    for root in search_roots or DEFAULT_PRETRAIN_OUTPUT_ROOTS:
        if root.exists():
            candidates.extend(root.rglob("pretrain_checkpoint.pt"))
            candidates.extend(root.rglob("tabnet_pretrainer.pt"))
    if not candidates:
        raise FileNotFoundError(
            "No embedding-pretrain checkpoint found. Run the pretrain stage first or pass --pretrain-checkpoint."
        )
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _load_checkpoint_payload(checkpoint_path: Path) -> dict[str, object]:
    try:
        payload = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    except TypeError:
        payload = torch.load(checkpoint_path, map_location="cpu")
    if not isinstance(payload, dict) or "config" not in payload or "input_dim" not in payload:
        raise ValueError(f"Invalid checkpoint payload: {checkpoint_path}")
    return payload


def _rebuild_pretrain_config(payload_config: dict[str, object], event_csv: Path) -> PretrainConfig:
    config = PretrainConfig()
    for key, value in payload_config.items():
        if key in {"input_csv", "output_root"}:
            continue
        if hasattr(config, key):
            setattr(config, key, value)
    config.input_csv = event_csv.resolve()
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


def build_embedding_bundle(config: V1Config) -> EmbeddingBundle:
    checkpoint_path = config.pretrain_checkpoint or discover_latest_checkpoint()
    payload = _load_checkpoint_payload(checkpoint_path)
    pretrain_config = _rebuild_pretrain_config(dict(payload["config"]), config.event_csv)

    prepared = prepare_pretraining_dataframe(pretrain_config)
    scaler = _load_scaler(checkpoint_path)

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
    attention_entropy = diagnostics.get("attention_entropy", 0.0)
    mask_density = diagnostics.get("mask_density", 0.0)
    if hasattr(attention_entropy, "cpu"):
        attention_entropy = attention_entropy.cpu().numpy()
    if hasattr(mask_density, "cpu"):
        mask_density = mask_density.cpu().numpy()
    dataframe["embedding_attention_entropy"] = attention_entropy
    dataframe["embedding_mask_density"] = mask_density

    return EmbeddingBundle(
        dataframe=dataframe,
        feature_columns=feature_columns,
        embedding_columns=embedding_columns,
        embeddings=embedding_array,
        checkpoint_path=checkpoint_path,
        checkpoint_config=dict(payload["config"]),
        split_counts=prepared.split_counts,
        split_slices=prepared.split_slices,
        embedding_dim=int(embedding_array.shape[1]),
    )
