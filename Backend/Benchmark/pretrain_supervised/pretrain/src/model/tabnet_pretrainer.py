from __future__ import annotations

import copy
import random
import time
from dataclasses import dataclass

import numpy as np
import torch
from torch import Tensor, nn
from torch.utils.data import DataLoader, TensorDataset

from Backend.Benchmark.pretrain_supervised.pretrain.src.config.settings import PretrainConfig
from Backend.Benchmark.pretrain_supervised.pretrain.src.model.decoder import TabNetDecoder
from Backend.Benchmark.pretrain_supervised.pretrain.src.model.encoder import TabNetEncoder
from Backend.Benchmark.pretrain_supervised.pretrain.src.model.losses import masked_mse_loss
from Backend.Benchmark.pretrain_supervised.pretrain.src.model.masking import RandomFeatureMasker
from Backend.Benchmark.pretrain_supervised.pretrain.src.monitoring.metrics import EpochMetrics


def set_global_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


@dataclass
class TrainingHistory:
    train_loss: list[float]
    validation_loss: list[float]
    best_epoch: int
    best_validation_loss: float
    stopped_early: bool
    epoch_metrics: list[dict[str, object]]

    def to_dict(self) -> dict[str, object]:
        return {
            "train_loss": self.train_loss,
            "validation_loss": self.validation_loss,
            "best_epoch": self.best_epoch,
            "best_validation_loss": self.best_validation_loss,
            "stopped_early": self.stopped_early,
            "epoch_metrics": self.epoch_metrics,
        }


class TabNetPretrainingModel(nn.Module):
    def __init__(self, input_dim: int, config: PretrainConfig) -> None:
        super().__init__()
        self.encoder = TabNetEncoder(input_dim=input_dim, config=config)
        self.decoder = TabNetDecoder(input_dim=input_dim, config=config)

    def encode(self, masked_inputs: Tensor) -> tuple[Tensor, dict[str, object]]:
        encoder_result = self.encoder(masked_inputs)
        embedding = encoder_result.aggregated_decision
        diagnostics = {
            "attention_entropy": float(encoder_result.attention_entropy.detach().cpu().item()),
            "mask_density": float(
                torch.stack([mask.mean() for mask in encoder_result.masks]).mean().detach().cpu().item()
            ),
        }
        return embedding, diagnostics

    def reconstruct(self, masked_inputs: Tensor) -> tuple[Tensor, dict[str, object]]:
        encoder_result = self.encoder(masked_inputs)
        reconstructed = self.decoder(encoder_result.decision_steps)
        diagnostics = {
            "attention_entropy": float(encoder_result.attention_entropy.detach().cpu().item()),
            "mask_density": float(
                torch.stack([mask.mean() for mask in encoder_result.masks]).mean().detach().cpu().item()
            ),
        }
        return reconstructed, diagnostics

    def forward(self, masked_inputs: Tensor) -> tuple[Tensor, dict[str, object]]:
        return self.reconstruct(masked_inputs)


class TabNetMaskedPretrainer:
    def __init__(self, config: PretrainConfig, input_dim: int) -> None:
        set_global_seed(config.seed)
        self.config = config
        self.input_dim = input_dim
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = TabNetPretrainingModel(input_dim=input_dim, config=config).to(self.device)
        self.masker = RandomFeatureMasker(feature_dim=input_dim, mask_ratio=config.mask_ratio)
        self.optimizer = torch.optim.Adam(
            self.model.parameters(),
            lr=config.learning_rate,
            weight_decay=config.weight_decay,
        )
        self._train_generator = torch.Generator(device="cpu")
        self._train_generator.manual_seed(config.seed)
        self._validation_seed = config.seed + 10_000
        self.history: TrainingHistory | None = None
        self.epoch_metrics: list[EpochMetrics] = []

    def _run_epoch(
        self,
        dataloader: DataLoader,
        *,
        train_mode: bool,
    ) -> tuple[float, dict[str, float]]:
        losses: list[float] = []
        attention_entropy_values: list[float] = []
        mask_density_values: list[float] = []
        grad_norm_values: list[float] = []
        if train_mode:
            self.model.train()
            generator = self._train_generator
        else:
            self.model.eval()
            generator = torch.Generator(device="cpu")
            generator.manual_seed(self._validation_seed)

        for (batch,) in dataloader:
            batch = batch.to(self.device)
            mask = self.masker.sample_mask(
                batch_size=batch.size(0),
                generator=generator,
                device=self.device,
            )
            masked_inputs = batch * (1.0 - mask)

            if train_mode:
                self.optimizer.zero_grad(set_to_none=True)
                reconstructed, diagnostics = self.model(masked_inputs)
                loss = masked_mse_loss(reconstructed, batch, mask)
                loss.backward()
                grad_norm = torch.nn.utils.clip_grad_norm_(self.model.parameters(), self.config.max_grad_norm)
                grad_norm_values.append(float(grad_norm.detach().cpu().item()))
                self.optimizer.step()
            else:
                with torch.no_grad():
                    reconstructed, diagnostics = self.model(masked_inputs)
                    loss = masked_mse_loss(reconstructed, batch, mask)

            losses.append(float(loss.detach().cpu().item()))
            attention_entropy_values.append(float(diagnostics["attention_entropy"]))
            mask_density_values.append(float(diagnostics["mask_density"]))

        if not losses:
            raise ValueError("Dataloader produced no batches.")
        summary = {
            "attention_entropy": float(np.mean(attention_entropy_values)),
            "mask_density": float(np.mean(mask_density_values)),
            "grad_norm": float(np.mean(grad_norm_values)) if grad_norm_values else 0.0,
        }
        return float(np.mean(losses)), summary

    def fit(self, train_features: np.ndarray, validation_features: np.ndarray) -> TrainingHistory:
        train_tensor = torch.tensor(train_features, dtype=torch.float32)
        validation_tensor = torch.tensor(validation_features, dtype=torch.float32)

        train_loader = DataLoader(
            TensorDataset(train_tensor),
            batch_size=self.config.batch_size,
            shuffle=True,
            drop_last=False,
        )
        validation_loader = DataLoader(
            TensorDataset(validation_tensor),
            batch_size=self.config.batch_size,
            shuffle=False,
            drop_last=False,
        )

        train_history: list[float] = []
        validation_history: list[float] = []
        best_epoch = -1
        best_validation_loss = float("inf")
        best_state = copy.deepcopy(self.model.state_dict())
        stopped_early = False
        epochs_without_improvement = 0

        for epoch_index in range(self.config.max_epochs):
            epoch_start = time.perf_counter()
            train_loss, train_summary = self._run_epoch(train_loader, train_mode=True)
            validation_loss, validation_summary = self._run_epoch(validation_loader, train_mode=False)
            epoch_seconds = float(time.perf_counter() - epoch_start)
            train_history.append(train_loss)
            validation_history.append(validation_loss)

            improvement = best_validation_loss - validation_loss
            if improvement > self.config.early_stopping_min_delta:
                best_validation_loss = validation_loss
                best_epoch = epoch_index
                best_state = copy.deepcopy(self.model.state_dict())
                epochs_without_improvement = 0
                should_stop = False
            else:
                epochs_without_improvement += 1
                should_stop = epochs_without_improvement >= self.config.patience

            self.epoch_metrics.append(
                EpochMetrics(
                    epoch=epoch_index,
                    train_loss=train_loss,
                    validation_loss=validation_loss,
                    best_validation_loss=float(best_validation_loss),
                    learning_rate=float(self.optimizer.param_groups[0]["lr"]),
                    attention_entropy=float(validation_summary["attention_entropy"]),
                    mask_density=float(validation_summary["mask_density"]),
                    grad_norm=float(train_summary["grad_norm"]),
                    epoch_seconds=epoch_seconds,
                    is_best_epoch=epoch_index == best_epoch,
                )
            )

            print(
                f"[epoch {epoch_index + 1}/{self.config.max_epochs}] "
                f"train_loss={train_loss:.6f} "
                f"val_loss={validation_loss:.6f} "
                f"best_val={best_validation_loss:.6f} "
                f"min_delta={self.config.early_stopping_min_delta:.6f} "
                f"grad_norm={train_summary['grad_norm']:.4f} "
                f"entropy={validation_summary['attention_entropy']:.4f} "
                f"time={epoch_seconds:.2f}s"
            )

            if should_stop:
                stopped_early = True
                break

        self.model.load_state_dict(best_state)
        self.history = TrainingHistory(
            train_loss=train_history,
            validation_loss=validation_history,
            best_epoch=best_epoch,
            best_validation_loss=float(best_validation_loss),
            stopped_early=stopped_early,
            epoch_metrics=[metric.to_dict() for metric in self.epoch_metrics],
        )
        return self.history

    def save_checkpoint(self, checkpoint_path: str, metadata: dict[str, object]) -> None:
        payload = {
            "state_dict": self.model.state_dict(),
            "input_dim": self.input_dim,
            "config": self.config.to_dict(),
            "metadata": metadata,
            "history": None if self.history is None else self.history.to_dict(),
            "epoch_metrics": [metric.to_dict() for metric in self.epoch_metrics],
            "model_class": self.model.__class__.__name__,
        }
        torch.save(payload, checkpoint_path)
