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

from Backend.Benchmark.shared.metrics import summarize_classification


def set_global_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


@dataclass(frozen=True)
class FTTransformerClassifierConfig:
    batch_size: int = 64
    max_epochs: int = 140
    patience: int = 18
    learning_rate: float = 8e-4
    weight_decay: float = 1e-4
    max_grad_norm: float = 1.0
    seed: int = 42
    token_dim: int = 48
    model_dim: int = 48
    num_heads: int = 6
    num_layers: int = 3
    ffn_multiplier: float = 4.0
    dropout: float = 0.15
    attention_dropout: float = 0.10
    residual_dropout: float = 0.0
    classifier_hidden_dim: int = 64

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class NumericalFeatureTokenizer(nn.Module):
    def __init__(self, num_features: int, token_dim: int) -> None:
        super().__init__()
        self.weight = nn.Parameter(torch.empty(num_features, token_dim))
        self.bias = nn.Parameter(torch.empty(num_features, token_dim))
        nn.init.xavier_uniform_(self.weight)
        nn.init.zeros_(self.bias)

    def forward(self, inputs: Tensor) -> Tensor:
        return inputs.unsqueeze(-1) * self.weight.unsqueeze(0) + self.bias.unsqueeze(0)


class FTTransformerBlock(nn.Module):
    def __init__(self, model_dim: int, num_heads: int, ffn_multiplier: float, dropout: float, attention_dropout: float, residual_dropout: float) -> None:
        super().__init__()
        hidden_dim = int(model_dim * ffn_multiplier)
        self.norm_attention = nn.LayerNorm(model_dim)
        self.attention = nn.MultiheadAttention(embed_dim=model_dim, num_heads=num_heads, dropout=attention_dropout, batch_first=True)
        self.attention_dropout = nn.Dropout(residual_dropout)
        self.norm_ffn = nn.LayerNorm(model_dim)
        self.ffn = nn.Sequential(
            nn.Linear(model_dim, hidden_dim),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, model_dim),
        )
        self.ffn_dropout = nn.Dropout(residual_dropout)

    def forward(self, inputs: Tensor) -> tuple[Tensor, Tensor]:
        normalized = self.norm_attention(inputs)
        attention_out, attention_map = self.attention(normalized, normalized, normalized, need_weights=True, average_attn_weights=False)
        hidden = inputs + self.attention_dropout(attention_out)
        hidden = hidden + self.ffn_dropout(self.ffn(self.norm_ffn(hidden)))
        return hidden, attention_map


class FTTransformerClassifier(nn.Module):
    def __init__(self, input_dim: int, output_dim: int, config: FTTransformerClassifierConfig) -> None:
        super().__init__()
        self.tokenizer = NumericalFeatureTokenizer(input_dim, config.token_dim)
        self.input_projection = nn.Identity() if config.token_dim == config.model_dim else nn.Linear(config.token_dim, config.model_dim)
        self.cls_token = nn.Parameter(torch.zeros(1, 1, config.model_dim))
        self.feature_embeddings = nn.Parameter(torch.zeros(1, input_dim + 1, config.model_dim))
        nn.init.normal_(self.cls_token, mean=0.0, std=0.02)
        nn.init.normal_(self.feature_embeddings, mean=0.0, std=0.02)
        self.dropout = nn.Dropout(config.dropout)
        self.blocks = nn.ModuleList(
            [
                FTTransformerBlock(config.model_dim, config.num_heads, config.ffn_multiplier, config.dropout, config.attention_dropout, config.residual_dropout)
                for _ in range(config.num_layers)
            ]
        )
        self.head = nn.Sequential(
            nn.LayerNorm(config.model_dim),
            nn.Linear(config.model_dim, config.classifier_hidden_dim),
            nn.GELU(),
            nn.Dropout(config.dropout),
            nn.Linear(config.classifier_hidden_dim, output_dim),
        )

    def forward(self, inputs: Tensor) -> tuple[Tensor, dict[str, float]]:
        feature_tokens = self.input_projection(self.tokenizer(inputs))
        cls = self.cls_token.expand(inputs.shape[0], -1, -1)
        tokens = self.dropout(torch.cat([cls, feature_tokens], dim=1) + self.feature_embeddings[:, : feature_tokens.shape[1] + 1, :])
        attention_entropy_values: list[Tensor] = []
        for block in self.blocks:
            tokens, attention_map = block(tokens)
            attention_prob = attention_map.mean(dim=1).clamp_min(1e-8)
            attention_entropy_values.append(-(attention_prob * attention_prob.log()).sum(dim=-1).mean())
        cls_representation = tokens[:, 0, :]
        logits = self.head(cls_representation)
        diagnostics = {
            "attention_entropy": float(torch.stack(attention_entropy_values).mean().detach().cpu().item()) if attention_entropy_values else 0.0,
            "cls_norm": float(cls_representation.norm(dim=1).mean().detach().cpu().item()),
            "token_std": float(tokens.std(dim=-1).mean().detach().cpu().item()),
        }
        return logits, diagnostics


@dataclass
class FTTransformerTrainResult:
    model: FTTransformerClassifier
    artifact_path: Path
    history: list[dict[str, float]]
    best_epoch: int
    best_validation_macro_f1: float
    best_validation_loss: float
    total_epochs_ran: int
    stop_reason: str
    total_train_seconds: float
    class_weights: list[float]
    device: str
    device_name: str


def train_ft_transformer_classifier(
    *,
    train_features: np.ndarray,
    train_labels: np.ndarray,
    validation_features: np.ndarray,
    validation_labels: np.ndarray,
    test_features: np.ndarray,
    test_labels: np.ndarray,
    class_names: list[str],
    input_dim: int,
    output_dim: int,
    config: FTTransformerClassifierConfig,
    artifact_path: Path,
    progress_label: str | None = None,
) -> FTTransformerTrainResult:
    set_global_seed(int(config.seed))
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    device_name = torch.cuda.get_device_name(device) if device.type == "cuda" else "cpu"
    if progress_label:
        if device.type == "cuda":
            print(f"[{progress_label}] device=cuda name={device_name} cuda_runtime={torch.version.cuda}")
        else:
            print(f"[{progress_label}] device=cpu cuda_available={torch.cuda.is_available()} torch_cuda={torch.version.cuda}")
    model = FTTransformerClassifier(input_dim=input_dim, output_dim=output_dim, config=config).to(device)
    train_loader = _make_loader(train_features, train_labels, batch_size=config.batch_size, shuffle=True, drop_last=True)
    validation_x = torch.tensor(validation_features, dtype=torch.float32, device=device)
    validation_y = torch.tensor(validation_labels, dtype=torch.long, device=device)
    test_x = torch.tensor(test_features, dtype=torch.float32, device=device)
    test_y = torch.tensor(test_labels, dtype=torch.long, device=device)
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
    stale_epochs = 0
    stop_reason = "max_epochs_reached"
    training_started_at = time.perf_counter()
    total_epochs_ran = 0
    for epoch in range(1, config.max_epochs + 1):
        total_epochs_ran = epoch
        epoch_start = time.perf_counter()
        model.train()
        epoch_losses: list[float] = []
        grad_norm_values: list[float] = []
        attention_entropy_values: list[float] = []
        cls_norm_values: list[float] = []
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
            cls_norm_values.append(float(diagnostics["cls_norm"]))
        model.eval()
        with torch.no_grad():
            validation_logits, validation_diagnostics = model(validation_x)
            validation_loss = float(loss_fn(validation_logits, validation_y).cpu().item())
            validation_predictions = validation_logits.argmax(dim=1).cpu().numpy()
            validation_metrics = summarize_classification(validation_labels, validation_predictions, class_names)
            test_logits, test_diagnostics = model(test_x)
            test_predictions = test_logits.argmax(dim=1).cpu().numpy()
            test_metrics = summarize_classification(test_labels, test_predictions, class_names)
        record = {
            "epoch": float(epoch),
            "train_loss": float(np.mean(epoch_losses)) if epoch_losses else float("nan"),
            "validation_loss": validation_loss,
            "validation_accuracy": float(validation_metrics["accuracy"]),
            "validation_balanced_accuracy": float(validation_metrics["balanced_accuracy"]),
            "validation_macro_f1": float(validation_metrics["macro_f1"]),
            "test_accuracy": float(test_metrics["accuracy"]),
            "test_balanced_accuracy": float(test_metrics["balanced_accuracy"]),
            "test_macro_f1": float(test_metrics["macro_f1"]),
            "attention_entropy": float(validation_diagnostics["attention_entropy"]),
            "cls_norm": float(validation_diagnostics["cls_norm"]),
            "token_std": float(validation_diagnostics["token_std"]),
            "grad_norm": float(np.mean(grad_norm_values)) if grad_norm_values else 0.0,
            "epoch_seconds": float(time.perf_counter() - epoch_start),
        }
        history.append(record)
        if progress_label:
            print(f"[{progress_label}] epoch {epoch}/{config.max_epochs} train_loss={record['train_loss']:.4f} val_loss={validation_loss:.4f} val_macro_f1={validation_metrics['macro_f1']:.4f} test_macro_f1={test_metrics['macro_f1']:.4f}")
        improved = validation_metrics["macro_f1"] > best_validation_macro_f1 + 1e-9 or (
            abs(validation_metrics["macro_f1"] - best_validation_macro_f1) <= 1e-9 and validation_loss < best_validation_loss
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
                "best_validation_loss": best_validation_loss,
                "history": history,
                "device": device.type,
                "device_name": device_name,
                "class_weights": class_weights.tolist(),
            }
            stale_epochs = 0
        else:
            stale_epochs += 1
            if stale_epochs >= config.patience:
                stop_reason = "early_stopping"
                if progress_label:
                    print(f"[{progress_label}] early stopping at epoch {epoch} after {stale_epochs} stale epochs.")
                break
    if best_state is None:
        best_state = {
            "state_dict": copy.deepcopy(model.state_dict()),
            "input_dim": input_dim,
            "output_dim": output_dim,
            "config": config.to_dict(),
            "best_epoch": best_epoch,
            "best_validation_macro_f1": best_validation_macro_f1,
            "best_validation_loss": best_validation_loss,
            "history": history,
            "device": device.type,
            "device_name": device_name,
            "class_weights": class_weights.tolist(),
        }
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(best_state, artifact_path)
    model.load_state_dict(best_state["state_dict"])
    model.eval()
    if progress_label:
        print(f"[{progress_label}] best_epoch={best_epoch} best_val_macro_f1={best_validation_macro_f1:.4f}")
    return FTTransformerTrainResult(
        model=model,
        artifact_path=artifact_path,
        history=history,
        best_epoch=int(best_epoch),
        best_validation_macro_f1=float(best_validation_macro_f1),
        best_validation_loss=float(best_validation_loss),
        total_epochs_ran=int(total_epochs_ran),
        stop_reason=stop_reason,
        total_train_seconds=float(time.perf_counter() - training_started_at),
        class_weights=class_weights.tolist(),
        device=device.type,
        device_name=device_name,
    )


def _make_loader(features: np.ndarray, labels: np.ndarray, batch_size: int, shuffle: bool, drop_last: bool) -> DataLoader:
    tensor_x = torch.tensor(features, dtype=torch.float32)
    tensor_y = torch.tensor(labels, dtype=torch.long)
    return DataLoader(TensorDataset(tensor_x, tensor_y), batch_size=batch_size, shuffle=shuffle, drop_last=drop_last)
