from __future__ import annotations

from torch import Tensor, nn

from Backend.Benchmark.pretrain_supervised.pretrain.src.model.activations import Sparsemax
from Backend.Benchmark.pretrain_supervised.pretrain.src.model.blocks import GhostBatchNorm


class AttentiveTransformer(nn.Module):
    def __init__(
        self,
        input_dim: int,
        attention_dim: int,
        virtual_batch_size: int,
        momentum: float,
        mask_type: str,
    ) -> None:
        super().__init__()
        self.linear = nn.Linear(input_dim, attention_dim, bias=False)
        self.batch_norm = GhostBatchNorm(
            input_dim=attention_dim,
            virtual_batch_size=virtual_batch_size,
            momentum=momentum,
        )
        if mask_type == "sparsemax":
            self.selector = Sparsemax(dim=-1)
        elif mask_type == "softmax":
            self.selector = nn.Softmax(dim=-1)
        else:
            raise ValueError(f"Unsupported mask_type: {mask_type}")

    def forward(self, attention_state: Tensor, prior_scales: Tensor) -> Tensor:
        scores = self.linear(attention_state)
        scores = self.batch_norm(scores)
        scores = scores * prior_scales
        return self.selector(scores)
