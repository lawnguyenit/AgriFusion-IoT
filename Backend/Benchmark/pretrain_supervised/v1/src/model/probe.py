from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from Backend.Benchmark.pretrain_supervised.v1.src.model.metrics import summarize_classification


class EmbeddingProbe(nn.Module):
    def __init__(self, input_dim: int, hidden_dim: int, output_dim: int, dropout: float) -> None:
        super().__init__()
        self.network = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, output_dim),
        )

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        return self.network(inputs)


@dataclass
class ProbeTrainResult:
    model: EmbeddingProbe
    artifact_path: Path
    history: list[dict[str, float]]
    best_epoch: int
    best_validation_macro_f1: float


def _make_loader(features: np.ndarray, labels: np.ndarray, batch_size: int, shuffle: bool) -> DataLoader:
    tensor_x = torch.tensor(features, dtype=torch.float32)
    tensor_y = torch.tensor(labels, dtype=torch.long)
    dataset = TensorDataset(tensor_x, tensor_y)
    return DataLoader(dataset, batch_size=batch_size, shuffle=shuffle)


def train_torch_probe(
    train_features: np.ndarray,
    train_labels: np.ndarray,
    validation_features: np.ndarray,
    validation_labels: np.ndarray,
    class_names: list[str],
    input_dim: int,
    output_dim: int,
    hidden_dim: int,
    dropout: float,
    batch_size: int,
    learning_rate: float,
    weight_decay: float,
    max_epochs: int,
    patience: int,
    max_grad_norm: float,
    seed: int,
    artifact_path: Path,
) -> ProbeTrainResult:
    torch.manual_seed(int(seed))
    np.random.seed(int(seed))

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = EmbeddingProbe(input_dim=input_dim, hidden_dim=hidden_dim, output_dim=output_dim, dropout=dropout).to(device)

    train_loader = _make_loader(train_features, train_labels, batch_size=batch_size, shuffle=True)
    validation_tensor_x = torch.tensor(validation_features, dtype=torch.float32, device=device)
    validation_tensor_y = torch.tensor(validation_labels, dtype=torch.long, device=device)

    class_counts = np.bincount(train_labels, minlength=output_dim).astype(np.float32)
    class_weights = class_counts.sum() / np.clip(class_counts, 1.0, None)
    class_weights = class_weights / class_weights.mean()
    loss_fn = nn.CrossEntropyLoss(weight=torch.tensor(class_weights, dtype=torch.float32, device=device))
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=weight_decay)

    history: list[dict[str, float]] = []
    best_state = None
    best_epoch = -1
    best_validation_macro_f1 = -1.0
    best_validation_loss = float("inf")
    epochs_without_improvement = 0

    for epoch in range(1, max_epochs + 1):
        model.train()
        epoch_losses = []
        for batch_x, batch_y in train_loader:
            batch_x = batch_x.to(device)
            batch_y = batch_y.to(device)
            optimizer.zero_grad(set_to_none=True)
            logits = model(batch_x)
            loss = loss_fn(logits, batch_y)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_grad_norm)
            optimizer.step()
            epoch_losses.append(float(loss.detach().cpu().item()))

        model.eval()
        with torch.no_grad():
            validation_logits = model(validation_tensor_x)
            validation_loss = float(loss_fn(validation_logits, validation_tensor_y).cpu().item())
            validation_predictions = validation_logits.argmax(dim=1).cpu().numpy()
            validation_metrics = summarize_classification(validation_labels, validation_predictions, class_names)

        train_loss = float(np.mean(epoch_losses)) if epoch_losses else float("nan")
        record = {
            "epoch": float(epoch),
            "train_loss": train_loss,
            "validation_loss": validation_loss,
            "validation_accuracy": float(validation_metrics["accuracy"]),
            "validation_macro_f1": float(validation_metrics["macro_f1"]),
        }
        history.append(record)

        improved = validation_metrics["macro_f1"] > best_validation_macro_f1 + 1e-9 or (
            abs(validation_metrics["macro_f1"] - best_validation_macro_f1) <= 1e-9
            and validation_loss < best_validation_loss
        )
        if improved:
            best_validation_macro_f1 = float(validation_metrics["macro_f1"])
            best_validation_loss = validation_loss
            best_epoch = epoch
            best_state = {
                "state_dict": model.state_dict(),
                "input_dim": input_dim,
                "hidden_dim": hidden_dim,
                "output_dim": output_dim,
                "dropout": dropout,
                "best_epoch": best_epoch,
                "best_validation_macro_f1": best_validation_macro_f1,
                "history": history,
            }
            epochs_without_improvement = 0
        else:
            epochs_without_improvement += 1
            if epochs_without_improvement >= patience:
                break

    if best_state is None:
        best_state = {
            "state_dict": model.state_dict(),
            "input_dim": input_dim,
            "hidden_dim": hidden_dim,
            "output_dim": output_dim,
            "dropout": dropout,
            "best_epoch": best_epoch,
            "best_validation_macro_f1": best_validation_macro_f1,
            "history": history,
        }

    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(best_state, artifact_path)
    model.load_state_dict(best_state["state_dict"])
    model.eval()
    return ProbeTrainResult(
        model=model,
        artifact_path=artifact_path,
        history=history,
        best_epoch=int(best_epoch),
        best_validation_macro_f1=float(best_validation_macro_f1),
    )
