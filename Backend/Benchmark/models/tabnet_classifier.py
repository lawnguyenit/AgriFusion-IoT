from __future__ import annotations

import copy
import math
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


class Sparsemax(nn.Module):
    def __init__(self, dim: int = -1) -> None:
        super().__init__()
        self.dim = dim

    def forward(self, inputs: Tensor) -> Tensor:
        shifted = inputs - inputs.max(dim=self.dim, keepdim=True).values
        sorted_inputs, _ = torch.sort(shifted, dim=self.dim, descending=True)
        cumulative = sorted_inputs.cumsum(self.dim) - 1.0
        range_values = torch.arange(1, sorted_inputs.size(self.dim) + 1, device=inputs.device, dtype=inputs.dtype)
        view_shape = [1] * sorted_inputs.dim()
        view_shape[self.dim] = -1
        range_values = range_values.view(view_shape)
        support = range_values * sorted_inputs > cumulative
        support_size = support.sum(dim=self.dim, keepdim=True).clamp_min(1)
        tau = cumulative.gather(self.dim, support_size - 1) / support_size.to(inputs.dtype)
        return torch.clamp(shifted - tau, min=0.0)


class GhostBatchNorm(nn.Module):
    def __init__(self, input_dim: int, virtual_batch_size: int, momentum: float) -> None:
        super().__init__()
        self.virtual_batch_size = virtual_batch_size
        self.batch_norm = nn.BatchNorm1d(input_dim, momentum=momentum)

    def forward(self, inputs: Tensor) -> Tensor:
        if inputs.size(0) <= self.virtual_batch_size:
            return self.batch_norm(inputs)
        chunks = inputs.chunk(int(math.ceil(inputs.size(0) / self.virtual_batch_size)), dim=0)
        return torch.cat([self.batch_norm(chunk) for chunk in chunks], dim=0)


class GLULayer(nn.Module):
    def __init__(self, input_dim: int, output_dim: int, virtual_batch_size: int, momentum: float) -> None:
        super().__init__()
        self.linear = nn.Linear(input_dim, output_dim * 2, bias=False)
        self.batch_norm = GhostBatchNorm(output_dim * 2, virtual_batch_size=virtual_batch_size, momentum=momentum)

    def forward(self, inputs: Tensor) -> Tensor:
        transformed = self.batch_norm(self.linear(inputs))
        left, gate = transformed.chunk(2, dim=1)
        return left * torch.sigmoid(gate)


class AttentiveTransformer(nn.Module):
    def __init__(self, input_dim: int, attention_dim: int, virtual_batch_size: int, momentum: float, mask_type: str) -> None:
        super().__init__()
        self.linear = nn.Linear(input_dim, attention_dim, bias=False)
        self.batch_norm = GhostBatchNorm(attention_dim, virtual_batch_size=virtual_batch_size, momentum=momentum)
        if mask_type == "sparsemax":
            self.selector = Sparsemax(dim=-1)
        elif mask_type == "softmax":
            self.selector = nn.Softmax(dim=-1)
        else:
            raise ValueError(f"Unsupported mask_type: {mask_type}")

    def forward(self, attention_state: Tensor, prior_scales: Tensor) -> Tensor:
        scores = self.batch_norm(self.linear(attention_state))
        return self.selector(scores * prior_scales)


class FeatureTransformer(nn.Module):
    def __init__(
        self,
        input_dim: int,
        output_dim: int,
        shared_layers: nn.ModuleList | None,
        n_independent: int,
        virtual_batch_size: int,
        momentum: float,
    ) -> None:
        super().__init__()
        self.shared_layers = shared_layers
        self.scale = math.sqrt(0.5)
        layers = []
        for layer_index in range(n_independent):
            layer_input_dim = input_dim if layer_index == 0 and not shared_layers else output_dim
            layers.append(GLULayer(layer_input_dim, output_dim, virtual_batch_size=virtual_batch_size, momentum=momentum))
        self.independent_layers = nn.ModuleList(layers)

    def forward(self, inputs: Tensor) -> Tensor:
        outputs = inputs
        if self.shared_layers is not None:
            for layer_index, layer in enumerate(self.shared_layers):
                transformed = layer(outputs)
                if layer_index == 0 and outputs.shape[1] != transformed.shape[1]:
                    outputs = transformed
                else:
                    outputs = (outputs + transformed) * self.scale
        for layer_index, layer in enumerate(self.independent_layers):
            transformed = layer(outputs)
            if self.shared_layers is None and layer_index == 0 and outputs.shape[1] != transformed.shape[1]:
                outputs = transformed
            else:
                outputs = (outputs + transformed) * self.scale
        return outputs


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


@dataclass
class EncoderForwardResult:
    decision_steps: list[Tensor]
    aggregated_decision: Tensor
    masks: list[Tensor]
    attention_entropy: Tensor


class TabNetEncoder(nn.Module):
    def __init__(self, input_dim: int, config: DirectTabNetClassifierConfig) -> None:
        super().__init__()
        transformer_dim = config.n_d + config.n_a
        vbs = min(config.virtual_batch_size, config.batch_size)
        self.n_d = config.n_d
        self.n_a = config.n_a
        self.n_steps = config.n_steps
        self.gamma = config.gamma
        self.initial_batch_norm = GhostBatchNorm(input_dim, virtual_batch_size=vbs, momentum=0.01)
        shared_initial_layers = (
            nn.ModuleList(
                [
                    GLULayer(input_dim if layer_index == 0 else transformer_dim, transformer_dim, virtual_batch_size=vbs, momentum=config.momentum)
                    for layer_index in range(config.n_shared)
                ]
            )
            if config.n_shared > 0
            else None
        )
        shared_step_layers = (
            nn.ModuleList(
                [
                    GLULayer(input_dim if layer_index == 0 else transformer_dim, transformer_dim, virtual_batch_size=vbs, momentum=config.momentum)
                    for layer_index in range(config.n_shared)
                ]
            )
            if config.n_shared > 0
            else None
        )
        self.initial_splitter = FeatureTransformer(
            input_dim=input_dim,
            output_dim=transformer_dim,
            shared_layers=shared_initial_layers,
            n_independent=config.n_independent,
            virtual_batch_size=vbs,
            momentum=config.momentum,
        )
        self.step_feature_transformers = nn.ModuleList(
            [
                FeatureTransformer(
                    input_dim=input_dim,
                    output_dim=transformer_dim,
                    shared_layers=shared_step_layers,
                    n_independent=config.n_independent,
                    virtual_batch_size=vbs,
                    momentum=config.momentum,
                )
                for _ in range(config.n_steps)
            ]
        )
        self.attentive_transformers = nn.ModuleList(
            [
                AttentiveTransformer(
                    input_dim=config.n_a,
                    attention_dim=input_dim,
                    virtual_batch_size=vbs,
                    momentum=config.momentum,
                    mask_type=config.mask_type,
                )
                for _ in range(config.n_steps)
            ]
        )

    def forward(self, inputs: Tensor) -> EncoderForwardResult:
        normalized_inputs = self.initial_batch_norm(inputs)
        initial_context = self.initial_splitter(normalized_inputs)
        attention_state = initial_context[:, self.n_d :]
        prior_scales = torch.ones_like(normalized_inputs)
        decision_steps: list[Tensor] = []
        masks: list[Tensor] = []
        entropy_terms: list[Tensor] = []
        for step_index in range(self.n_steps):
            mask_values = self.attentive_transformers[step_index](attention_state, prior_scales)
            prior_scales = prior_scales * (self.gamma - mask_values)
            transformed = self.step_feature_transformers[step_index](mask_values * normalized_inputs)
            decision_output = torch.relu(transformed[:, : self.n_d])
            attention_state = transformed[:, self.n_d :]
            decision_steps.append(decision_output)
            masks.append(mask_values)
            entropy_terms.append(-(mask_values * torch.log(mask_values + 1e-15)).sum(dim=1).mean())
        aggregated = torch.stack(decision_steps, dim=0).sum(dim=0)
        mean_entropy = torch.stack(entropy_terms).mean() if entropy_terms else torch.tensor(0.0, device=inputs.device)
        return EncoderForwardResult(
            decision_steps=decision_steps,
            aggregated_decision=aggregated,
            masks=masks,
            attention_entropy=mean_entropy,
        )


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


def train_direct_tabnet_classifier(
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
    config: DirectTabNetClassifierConfig,
    artifact_path: Path,
    progress_label: str | None = None,
) -> DirectTabNetTrainResult:
    set_global_seed(int(config.seed))
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if progress_label:
        if device.type == "cuda":
            print(f"[{progress_label}] device=cuda name={torch.cuda.get_device_name(device)} cuda_runtime={torch.version.cuda}")
        else:
            print(f"[{progress_label}] device=cpu cuda_available={torch.cuda.is_available()} torch_cuda={torch.version.cuda}")
    model = DirectTabNetClassifier(input_dim=input_dim, output_dim=output_dim, config=config).to(device)
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
            validation_logits, validation_diagnostics = model(validation_x)
            validation_loss = float(loss_fn(validation_logits, validation_y).cpu().item())
            validation_predictions = validation_logits.argmax(dim=1).cpu().numpy()
            validation_metrics = summarize_classification(validation_labels, validation_predictions, class_names)
            test_logits, _ = model(test_x)
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
            "mask_density": float(validation_diagnostics["mask_density"]),
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
                "history": history,
                "model_class": model.__class__.__name__,
            }
            stale_epochs = 0
        else:
            stale_epochs += 1
            if stale_epochs >= config.patience:
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


def _make_loader(features: np.ndarray, labels: np.ndarray, batch_size: int, shuffle: bool, drop_last: bool) -> DataLoader:
    tensor_x = torch.tensor(features, dtype=torch.float32)
    tensor_y = torch.tensor(labels, dtype=torch.long)
    return DataLoader(TensorDataset(tensor_x, tensor_y), batch_size=batch_size, shuffle=shuffle, drop_last=drop_last)
