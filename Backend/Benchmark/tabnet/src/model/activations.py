from __future__ import annotations

import torch
from torch import Tensor, nn


class Sparsemax(nn.Module):
    def __init__(self, dim: int = -1) -> None:
        super().__init__()
        self.dim = dim

    def forward(self, inputs: Tensor) -> Tensor:
        dim = self.dim
        shifted = inputs - inputs.max(dim=dim, keepdim=True).values
        sorted_inputs, _ = torch.sort(shifted, dim=dim, descending=True)

        cumulative = sorted_inputs.cumsum(dim) - 1.0
        range_values = torch.arange(
            1,
            sorted_inputs.size(dim) + 1,
            device=inputs.device,
            dtype=inputs.dtype,
        )
        view_shape = [1] * sorted_inputs.dim()
        view_shape[dim] = -1
        range_values = range_values.view(view_shape)

        support = range_values * sorted_inputs > cumulative
        support_size = support.sum(dim=dim, keepdim=True).clamp_min(1)
        tau = cumulative.gather(dim, support_size - 1) / support_size.to(inputs.dtype)
        return torch.clamp(shifted - tau, min=0.0)
