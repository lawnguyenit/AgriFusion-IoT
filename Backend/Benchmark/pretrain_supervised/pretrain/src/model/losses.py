from __future__ import annotations

from torch import Tensor


def masked_mse_loss(reconstructed: Tensor, target: Tensor, mask: Tensor) -> Tensor:
    squared_error = (reconstructed - target) ** 2
    masked_error = squared_error * mask
    normalizer = mask.sum().clamp_min(1.0)
    return masked_error.sum() / normalizer
