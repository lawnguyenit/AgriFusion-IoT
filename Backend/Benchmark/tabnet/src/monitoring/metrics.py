from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass
class EpochMetrics:
    epoch: int
    train_loss: float
    validation_loss: float
    best_validation_loss: float
    learning_rate: float
    attention_entropy: float
    mask_density: float
    grad_norm: float
    epoch_seconds: float
    is_best_epoch: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
