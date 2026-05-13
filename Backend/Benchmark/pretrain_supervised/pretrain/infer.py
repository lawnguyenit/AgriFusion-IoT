from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from Backend.Benchmark.pretrain_supervised.pretrain.src.config.settings import PretrainConfig
from Backend.Benchmark.pretrain_supervised.pretrain.src.data.preprocessing import prepare_pretraining_dataframe
from Backend.Benchmark.pretrain_supervised.pretrain.src.model.tabnet_pretrainer import TabNetPretrainingModel


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Load a trained pretrain checkpoint and export embeddings or reconstruction scores."
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        required=True,
        help="Path to pretrain_checkpoint.pt from a completed run folder.",
    )
    parser.add_argument(
        "--input-csv",
        type=Path,
        help="Optional input CSV to transform. Defaults to the training input CSV stored in the checkpoint config.",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        required=True,
        help="Where to save the exported result.",
    )
    parser.add_argument(
        "--mode",
        choices=("embedding", "reconstruction"),
        default="embedding",
        help="What to export from the trained model.",
    )
    return parser.parse_args()


def load_model(checkpoint_path: Path) -> tuple[TabNetPretrainingModel, dict[str, object]]:
    try:
        payload = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    except TypeError:
        payload = torch.load(checkpoint_path, map_location="cpu")
    config_payload = dict(payload["config"])
    config = PretrainConfig()
    for key, value in config_payload.items():
        if key in {"input_csv", "output_root"}:
            continue
        if hasattr(config, key):
            setattr(config, key, value)
    model = TabNetPretrainingModel(input_dim=int(payload["input_dim"]), config=config)
    model.load_state_dict(payload["state_dict"])
    model.eval()
    return model, payload


def load_scaler(checkpoint_path: Path):
    scaler_stats_path = checkpoint_path.parent / "scaler_stats.json"
    if scaler_stats_path.exists():
        with scaler_stats_path.open("r", encoding="utf-8") as handle:
            stats = json.load(handle)
        from sklearn.preprocessing import StandardScaler

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


def prepare_features(input_csv: Path, config: PretrainConfig) -> pd.DataFrame:
    prepared = prepare_pretraining_dataframe(config)
    return prepared.dataframe, prepared.feature_columns


def main() -> None:
    args = parse_args()
    model, payload = load_model(args.checkpoint)
    scaler = load_scaler(args.checkpoint)

    config = PretrainConfig()
    for key, value in dict(payload["config"]).items():
        if key in {"input_csv", "output_root"}:
            continue
        if hasattr(config, key):
            setattr(config, key, value)

    input_csv = args.input_csv or Path(payload["config"]["input_csv"])
    config.input_csv = input_csv.resolve()
    prepared = prepare_pretraining_dataframe(config)
    dataframe = prepared.dataframe
    feature_columns = prepared.feature_columns

    scaled_features = scaler.transform(dataframe[feature_columns])
    batch = torch.tensor(scaled_features, dtype=torch.float32)

    with torch.no_grad():
        if args.mode == "embedding":
            embeddings, diagnostics = model.encode(batch)
            output = dataframe[["timestamp", "split"]].copy()
            embedding_array = embeddings.cpu().numpy()
            for index in range(embedding_array.shape[1]):
                output[f"tabnet_emb_{index}"] = embedding_array[:, index]
            output["attention_entropy"] = diagnostics["attention_entropy"]
            output["mask_density"] = diagnostics["mask_density"]
        else:
            reconstruction, diagnostics = model.reconstruct(batch)
            reconstruction_array = reconstruction.cpu().numpy()
            output = dataframe[["timestamp", "split"]].copy()
            for index, column in enumerate(feature_columns):
                output[f"recon_{column}"] = reconstruction_array[:, index]
            output["attention_entropy"] = diagnostics["attention_entropy"]
            output["mask_density"] = diagnostics["mask_density"]
            target = batch.cpu().numpy()
            mse = np.mean((reconstruction_array - target) ** 2, axis=1)
            output["reconstruction_mse"] = mse

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(args.output_csv, index=False)
    print(f"Exported {len(output)} rows to {args.output_csv}")


if __name__ == "__main__":
    main()
