from __future__ import annotations

import math

from torch import Tensor, nn

from Backend.Benchmark.tabnet.src.model.blocks import GLULayer


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
        self.output_dim = output_dim
        self.scale = math.sqrt(0.5)

        independent_layers = []
        for layer_index in range(n_independent):
            layer_input_dim = input_dim if layer_index == 0 and not shared_layers else output_dim
            independent_layers.append(
                GLULayer(
                    input_dim=layer_input_dim,
                    output_dim=output_dim,
                    virtual_batch_size=virtual_batch_size,
                    momentum=momentum,
                )
            )
        self.independent_layers = nn.ModuleList(independent_layers)

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
