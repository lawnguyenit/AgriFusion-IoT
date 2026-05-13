from __future__ import annotations

from torch import Tensor, nn

from Backend.Benchmark.pretrain_supervised.pretrain.src.config.settings import PretrainConfig
from Backend.Benchmark.pretrain_supervised.pretrain.src.model.feature_transformer import FeatureTransformer


class TabNetDecoder(nn.Module):
    def __init__(self, input_dim: int, config: PretrainConfig) -> None:
        super().__init__()
        decoder_dim = config.n_d
        self.step_decoders = nn.ModuleList(
            [
                FeatureTransformer(
                    input_dim=decoder_dim,
                    output_dim=decoder_dim,
                    shared_layers=None,
                    n_independent=config.n_indep_decoder,
                    virtual_batch_size=min(config.virtual_batch_size, config.batch_size),
                    momentum=config.momentum,
                )
                for _ in range(config.n_steps)
            ]
        )
        self.reconstruction_head = nn.Linear(decoder_dim, input_dim, bias=False)

    def forward(self, decision_steps: list[Tensor]) -> Tensor:
        decoded_steps = [
            step_decoder(step_output)
            for step_decoder, step_output in zip(self.step_decoders, decision_steps)
        ]
        combined = decoded_steps[0]
        for decoded in decoded_steps[1:]:
            combined = combined + decoded
        return self.reconstruction_head(combined)
