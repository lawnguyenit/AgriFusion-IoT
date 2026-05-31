from __future__ import annotations

from Backend.Benchmark.direct_benchmark.src.data.contracts import DirectDataBundle
from Backend.Benchmark.direct_benchmark.src.data.raw_data import build_direct_data_bundle
from Backend.Benchmark.tabpfn_benchmark.src.config.settings import TabPFNBenchmarkConfig


def build_tabpfn_data_bundle(config: TabPFNBenchmarkConfig, experiment_name: str) -> DirectDataBundle:
    return build_direct_data_bundle(config=config, experiment_name=experiment_name)
