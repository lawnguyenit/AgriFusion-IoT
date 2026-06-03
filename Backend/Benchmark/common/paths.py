from __future__ import annotations

from pathlib import Path

from Backend.Config.paths import BACKEND_PATHS


BACKEND_ROOT: Path = BACKEND_PATHS.backend_dir
BENCHMARK_ROOT: Path = BACKEND_PATHS.benchmark_dir
SIMULATOR_ROOT: Path = BACKEND_PATHS.simulator_dir

FUZZY_LOGIC_BASIC_ROOT: Path = BENCHMARK_ROOT / "fuzzy_logic_basic"
FUZZY_LOGIC_BASIC_DATASET_ROOT: Path = FUZZY_LOGIC_BASIC_ROOT / "dataset"

PRETRAIN_SUPERVISED_ROOT: Path = BENCHMARK_ROOT / "pretrain_supervised"
PRETRAIN_ROOT: Path = PRETRAIN_SUPERVISED_ROOT / "pretrain"

DIRECT_BENCHMARK_ROOT: Path = BENCHMARK_ROOT / "direct_benchmark"
FT_TRANSFORMER_BENCHMARK_ROOT: Path = BENCHMARK_ROOT / "ft_transformer_benchmark"
TABPFN_BENCHMARK_ROOT: Path = BENCHMARK_ROOT / "tabpfn_benchmark"
CONTEXT_CLASSIFIER_ROOT: Path = BENCHMARK_ROOT / "context_classifier"

# Legacy artifact root retained because older benchmark checkpoints may still live here.
TABNET_BENCHMARK_ROOT: Path = BENCHMARK_ROOT / "tabnet"
