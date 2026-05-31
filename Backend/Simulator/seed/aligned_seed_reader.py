from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from Backend.Benchmark.fuzzy_logic_basic.layer1.alignment import align_layer1_records
from Backend.Benchmark.fuzzy_logic_basic.layer1.config import AlignmentConfig
from Backend.Benchmark.fuzzy_logic_basic.layer1.ec_npk_consistency import ECConsistencyModel


@dataclass(frozen=True)
class AlignedSeedDataset:
    rows: list[dict[str, float | int | None]]
    ec_model: ECConsistencyModel
    input_counts: dict[str, int]
    missing_counts: dict[str, int]
    flag_distribution: dict[str, int]


def load_aligned_seed_rows(layer1_root: Path) -> AlignedSeedDataset:
    rows, input_counts, missing_counts, ec_model, flag_distribution = align_layer1_records(
        AlignmentConfig(input_root=layer1_root)
    )
    if not rows:
        raise ValueError(f"Khong tim thay du lieu Layer1 de seed simulator tai {layer1_root}")
    rows = sorted(rows, key=lambda item: int(item["timestamp"]))
    return AlignedSeedDataset(
        rows=rows,
        ec_model=ec_model,
        input_counts=input_counts,
        missing_counts=missing_counts,
        flag_distribution=flag_distribution,
    )
