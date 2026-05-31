from __future__ import annotations

import copy
import random
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import torch
from torch import Tensor, nn
from torch.utils.data import DataLoader, TensorDataset

from Backend.Benchmark.pretrain_supervised.pretrain.src.model.encoder import TabNetEncoder
from Backend.Benchmark.pretrain_supervised.v1.src.model.metrics import summarize_classification


def set_global_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


@dataclass(frozen=True)
class DirectTabNetClassifierConfig:
    batch_size: int = 64
    virtual_batch_size: int = 32
    max_epochs: int = 120
    patience: int = 16
    early_stopping_min_delta: float = 1e-3
    learning_rate: float = 1e-3
    weight_decay: float = 1e-4
    max_grad_norm: float = 1.0
    seed: int = 42
    n_d: int = 16
    n_a: int = 16
    n_steps: int = 4
    gamma: float = 1.3
    n_independent: int = 2
    n_shared: int = 2
    momentum: float = 0.02
    mask_type: str = "sparsemax"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class DirectTabNetClassifier(nn.Module):
    def __init__(self, input_dim: int, output_dim: int, config: DirectTabNetClassifierConfig) -> None:
        super().__init__()
        self.encoder = TabNetEncoder(input_dim=input_dim, config=config)
        self.classifier = nn.Linear(config.n_d, output_dim)

    def forward(self, inputs: Tensor) -> tuple[Tensor, dict[str, object]]:
        encoder_result = self.encoder(inputs)
        logits = self.classifier(encoder_result.aggregated_decision)
        diagnostics = {
            "attention_entropy": float(encoder_result.attention_entropy.detach().cpu().item()),
            "mask_density": float(torch.stack([mask.mean() for mask in encoder_result.masks]).mean().detach().cpu().item()),
        }
        return logits, diagnostics


@dataclass
class DirectTabNetTrainResult:
    model: DirectTabNetClassifier
    artifact_path: Path
    history: list[dict[str, float]]
    best_epoch: int
    best_validation_macro_f1: float


def _make_loader(features: np.ndarray, labels: np.ndarray, batch_size: int, shuffle: bool, drop_last: bool) -> DataLoader:
    tensor_x = torch.tensor(features, dtype=torch.float32)
    tensor_y = torch.tensor(labels, dtype=torch.long)
    dataset = TensorDataset(tensor_x, tensor_y)
    return DataLoader(dataset, batch_size=batch_size, shuffle=shuffle, drop_last=drop_last)


def train_direct_tabnet_classifier(
    train_features: np.ndarray,
    train_labels: np.ndarray,
    validation_features: np.ndarray,
    validation_labels: np.ndarray,
    test_features: np.ndarray,
    test_labels: np.ndarray,
    class_names: list[str],
    input_dim: int,
    output_dim: int,
    config: DirectTabNetClassifierConfig,
    artifact_path: Path,
    progress_label: str | None = None,
) -> DirectTabNetTrainResult:
    set_global_seed(int(config.seed))
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if progress_label:
        if device.type == "cuda":
            print(
                f"[{progress_label}] device=cuda "
                f"name={torch.cuda.get_device_name(device)} "
                f"cuda_runtime={torch.version.cuda}"
            )
        else:
            print(f"[{progress_label}] device=cpu cuda_available={torch.cuda.is_available()} torch_cuda={torch.version.cuda}")
    model = DirectTabNetClassifier(input_dim=input_dim, output_dim=output_dim, config=config).to(device)

    train_loader = _make_loader(train_features, train_labels, batch_size=config.batch_size, shuffle=True, drop_last=True)
    validation_tensor_x = torch.tensor(validation_features, dtype=torch.float32, device=device)
    validation_tensor_y = torch.tensor(validation_labels, dtype=torch.long, device=device)
    test_tensor_x = torch.tensor(test_features, dtype=torch.float32, device=device)
    test_tensor_y = torch.tensor(test_labels, dtype=torch.long, device=device)

    class_counts = np.bincount(train_labels, minlength=output_dim).astype(np.float32)
    class_weights = class_counts.sum() / np.clip(class_counts, 1.0, None)
    class_weights = class_weights / class_weights.mean()
    loss_fn = nn.CrossEntropyLoss(weight=torch.tensor(class_weights, dtype=torch.float32, device=device))
    optimizer = torch.optim.AdamW(model.parameters(), lr=config.learning_rate, weight_decay=config.weight_decay)

    history: list[dict[str, float]] = []
    best_state: dict[str, object] | None = None
    best_epoch = -1
    best_validation_macro_f1 = -1.0
    best_validation_loss = float("inf")
    epochs_without_improvement = 0

    for epoch in range(1, config.max_epochs + 1):
        epoch_start = time.perf_counter()
        model.train()
        epoch_losses: list[float] = []
        grad_norm_values: list[float] = []
        attention_entropy_values: list[float] = []
        mask_density_values: list[float] = []

        for batch_x, batch_y in train_loader:
            batch_x = batch_x.to(device)
            batch_y = batch_y.to(device)
            optimizer.zero_grad(set_to_none=True)
            logits, diagnostics = model(batch_x)
            loss = loss_fn(logits, batch_y)
            loss.backward()
            grad_norm = torch.nn.utils.clip_grad_norm_(model.parameters(), config.max_grad_norm)
            optimizer.step()
            epoch_losses.append(float(loss.detach().cpu().item()))
            grad_norm_values.append(float(grad_norm.detach().cpu().item()))
            attention_entropy_values.append(float(diagnostics["attention_entropy"]))
            mask_density_values.append(float(diagnostics["mask_density"]))

        model.eval()
        with torch.no_grad():
            validation_logits, validation_diagnostics = model(validation_tensor_x)
            validation_loss = float(loss_fn(validation_logits, validation_tensor_y).cpu().item())
            validation_predictions = validation_logits.argmax(dim=1).cpu().numpy()
            validation_metrics = summarize_classification(validation_labels, validation_predictions, class_names)

            test_logits, _ = model(test_tensor_x)
            test_predictions = test_logits.argmax(dim=1).cpu().numpy()
            test_metrics = summarize_classification(test_labels, test_predictions, class_names)

        train_loss = float(np.mean(epoch_losses)) if epoch_losses else float("nan")
        epoch_seconds = float(time.perf_counter() - epoch_start)
        record = {
            "epoch": float(epoch),
            "train_loss": train_loss,
            "validation_loss": validation_loss,
            "validation_accuracy": float(validation_metrics["accuracy"]),
            "validation_balanced_accuracy": float(validation_metrics["balanced_accuracy"]),
            "validation_macro_f1": float(validation_metrics["macro_f1"]),
            "test_accuracy": float(test_metrics["accuracy"]),
            "test_balanced_accuracy": float(test_metrics["balanced_accuracy"]),
            "test_macro_f1": float(test_metrics["macro_f1"]),
            "attention_entropy": float(validation_diagnostics["attention_entropy"]),
            "mask_density": float(validation_diagnostics["mask_density"]),
            "grad_norm": float(np.mean(grad_norm_values)) if grad_norm_values else 0.0,
            "epoch_seconds": epoch_seconds,
        }
        history.append(record)
        if progress_label:
            print(
                f"[{progress_label}] epoch {epoch}/{config.max_epochs} "
                f"train_loss={train_loss:.4f} val_loss={validation_loss:.4f} "
                f"val_macro_f1={validation_metrics['macro_f1']:.4f} "
                f"test_macro_f1={test_metrics['macro_f1']:.4f}"
            )

        improved = validation_metrics["macro_f1"] > best_validation_macro_f1 + 1e-9 or (
            abs(validation_metrics["macro_f1"] - best_validation_macro_f1) <= 1e-9
            and validation_loss < best_validation_loss
        )
        if improved:
            best_validation_macro_f1 = float(validation_metrics["macro_f1"])
            best_validation_loss = validation_loss
            best_epoch = epoch
            best_state = {
                "state_dict": copy.deepcopy(model.state_dict()),
                "input_dim": input_dim,
                "output_dim": output_dim,
                "config": config.to_dict(),
                "best_epoch": best_epoch,
                "best_validation_macro_f1": best_validation_macro_f1,
                "history": history,
                "model_class": model.__class__.__name__,
            }
            epochs_without_improvement = 0
        else:
            epochs_without_improvement += 1
            if epochs_without_improvement >= config.patience:
                if progress_label:
                    print(f"[{progress_label}] early stopping at epoch {epoch} after {epochs_without_improvement} stale epochs.")
                break

    if best_state is None:
        best_state = {
            "state_dict": copy.deepcopy(model.state_dict()),
            "input_dim": input_dim,
            "output_dim": output_dim,
            "config": config.to_dict(),
            "best_epoch": best_epoch,
            "best_validation_macro_f1": best_validation_macro_f1,
            "history": history,
            "model_class": model.__class__.__name__,
        }

    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(best_state, artifact_path)
    model.load_state_dict(best_state["state_dict"])
    model.eval()
    if progress_label:
        print(f"[{progress_label}] best_epoch={best_epoch} best_val_macro_f1={best_validation_macro_f1:.4f}")
    return DirectTabNetTrainResult(
        model=model,
        artifact_path=artifact_path,
        history=history,
        best_epoch=int(best_epoch),
        best_validation_macro_f1=float(best_validation_macro_f1),
    )
