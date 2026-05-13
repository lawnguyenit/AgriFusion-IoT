from __future__ import annotations

from dataclasses import dataclass

import torch
from torch import Tensor, nn

from Backend.Benchmark.pretrain_supervised.pretrain.src.config.settings import PretrainConfig
from Backend.Benchmark.pretrain_supervised.pretrain.src.model.attentive_transformer import AttentiveTransformer
from Backend.Benchmark.pretrain_supervised.pretrain.src.model.blocks import GhostBatchNorm, GLULayer
from Backend.Benchmark.pretrain_supervised.pretrain.src.model.feature_transformer import FeatureTransformer


@dataclass
class EncoderForwardResult:
    decision_steps: list[Tensor]
    aggregated_decision: Tensor
    masks: list[Tensor]
    attention_entropy: Tensor


class TabNetEncoder(nn.Module):
    def __init__(self, input_dim: int, config: PretrainConfig) -> None:
        super().__init__()
        transformer_dim = config.n_d + config.n_a

        self.input_dim = input_dim
        self.n_d = config.n_d
        self.n_a = config.n_a
        self.n_steps = config.n_steps
        self.gamma = config.gamma
        self.initial_batch_norm = GhostBatchNorm(
            input_dim=input_dim,
            virtual_batch_size=min(config.virtual_batch_size, config.batch_size),
            momentum=0.01,
        )

        shared_initial_layers = nn.ModuleList(
            [
                GLULayer(
                    input_dim=input_dim if layer_index == 0 else transformer_dim,
                    output_dim=transformer_dim,
                    virtual_batch_size=min(config.virtual_batch_size, config.batch_size),
                    momentum=config.momentum,
                )
                for layer_index in range(config.n_shared)
            ]
        ) if config.n_shared > 0 else None

        shared_step_layers = nn.ModuleList(
            [
                GLULayer(
                    input_dim=input_dim if layer_index == 0 else transformer_dim,
                    output_dim=transformer_dim,
                    virtual_batch_size=min(config.virtual_batch_size, config.batch_size),
                    momentum=config.momentum,
                )
                for layer_index in range(config.n_shared)
            ]
        ) if config.n_shared > 0 else None

        self.initial_splitter = FeatureTransformer(
            input_dim=input_dim,
            output_dim=transformer_dim,
            shared_layers=shared_initial_layers,
            n_independent=config.n_independent,
            virtual_batch_size=min(config.virtual_batch_size, config.batch_size),
            momentum=config.momentum,
        )
        self.step_feature_transformers = nn.ModuleList(
            [
                FeatureTransformer(
                    input_dim=input_dim,
                    output_dim=transformer_dim,
                    shared_layers=shared_step_layers,
                    n_independent=config.n_independent,
                    virtual_batch_size=min(config.virtual_batch_size, config.batch_size),
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
                    virtual_batch_size=min(config.virtual_batch_size, config.batch_size),
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

            masked_inputs = mask_values * normalized_inputs
            transformed = self.step_feature_transformers[step_index](masked_inputs)
            decision_output = torch.relu(transformed[:, : self.n_d])
            attention_state = transformed[:, self.n_d :]

            decision_steps.append(decision_output)
            masks.append(mask_values)
            entropy_terms.append(
                -(mask_values * torch.log(mask_values + 1e-15)).sum(dim=1).mean()
            )

        aggregated = torch.stack(decision_steps, dim=0).sum(dim=0)
        mean_entropy = torch.stack(entropy_terms).mean() if entropy_terms else torch.tensor(0.0, device=inputs.device)
        return EncoderForwardResult(
            decision_steps=decision_steps,
            aggregated_decision=aggregated,
            masks=masks,
            attention_entropy=mean_entropy,
        )
