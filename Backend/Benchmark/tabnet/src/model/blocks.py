from __future__ import annotations

import math

import torch
from torch import Tensor, nn


class GhostBatchNorm(nn.Module):
    def __init__(self, input_dim: int, virtual_batch_size: int, momentum: float) -> None:
        super().__init__()
        self.input_dim = input_dim
        self.virtual_batch_size = virtual_batch_size
        self.batch_norm = nn.BatchNorm1d(input_dim, momentum=momentum)

    def forward(self, inputs: Tensor) -> Tensor:
        if inputs.size(0) <= self.virtual_batch_size:
            return self.batch_norm(inputs)

        chunks = inputs.chunk(int(math.ceil(inputs.size(0) / self.virtual_batch_size)), dim=0)
        normalized_chunks = [self.batch_norm(chunk) for chunk in chunks]
        return torch.cat(normalized_chunks, dim=0)


class GLULayer(nn.Module):
    def __init__(
        self,
        input_dim: int,
        output_dim: int,
        virtual_batch_size: int,
        momentum: float,
    ) -> None:
        super().__init__()
        self.output_dim = output_dim
        self.linear = nn.Linear(input_dim, output_dim * 2, bias=False)
        self.batch_norm = GhostBatchNorm(
            input_dim=output_dim * 2,
            virtual_batch_size=virtual_batch_size,
            momentum=momentum,
        )

    def forward(self, inputs: Tensor) -> Tensor:
        transformed = self.linear(inputs)
        transformed = self.batch_norm(transformed)
        left, gate = transformed.chunk(2, dim=1)
        return left * torch.sigmoid(gate)
