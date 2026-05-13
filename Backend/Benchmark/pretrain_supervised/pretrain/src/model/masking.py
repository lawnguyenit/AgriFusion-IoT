from __future__ import annotations

import torch
from torch import Tensor


class RandomFeatureMasker:
    def __init__(self, feature_dim: int, mask_ratio: float) -> None:
        self.feature_dim = feature_dim
        self.mask_ratio = mask_ratio

    def sample_mask(
        self,
        batch_size: int,
        *,
        generator: torch.Generator,
        device: torch.device,
    ) -> Tensor:
        mask = (torch.rand((batch_size, self.feature_dim), generator=generator) < self.mask_ratio).float()
        empty_rows = mask.sum(dim=1) == 0
        if empty_rows.any():
            forced_indices = torch.randint(
                low=0,
                high=self.feature_dim,
                size=(int(empty_rows.sum().item()),),
                generator=generator,
            )
            row_indices = torch.nonzero(empty_rows, as_tuple=False).flatten()
            mask[row_indices, forced_indices] = 1.0
        return mask.to(device)
