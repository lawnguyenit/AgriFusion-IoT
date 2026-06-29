from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .env import BACKEND_DIR, SERVICES_DIR


@dataclass(frozen=True)
class BackendPaths:
    backend_dir: Path = field(default_factory=lambda: BACKEND_DIR.resolve())
    services_dir: Path = field(default_factory=lambda: SERVICES_DIR.resolve())

    @property
    def config_dir(self) -> Path:
        return self.backend_dir / "Config"

    @property
    def core_dir(self) -> Path:
        return self.backend_dir / "Core"

    @property
    def benchmark_dir(self) -> Path:
        return self.backend_dir / "Benchmark"

    @property
    def output_data_dir(self) -> Path:
        return self.backend_dir / "Output_data"

    @property
    def layer0_dir(self) -> Path:
        return self.output_data_dir / "Layer0"

    @property
    def layer1_dir(self) -> Path:
        return self.output_data_dir / "Layer1"

    @property
    def super_table_dir(self) -> Path:
        return self.output_data_dir / "SuperTable"

    @property
    def result_publish_dir(self) -> Path:
        return self.output_data_dir / "Result_publish"

    @property
    def navigation_dir(self) -> Path:
        return self.backend_dir / "Navigation"

    @property
    def simulator_dir(self) -> Path:
        return self.backend_dir / "Simulator"

    def ensure_directory(self, path: Path) -> Path:
        path.mkdir(parents=True, exist_ok=True)
        return path

    def relative_to_backend(self, target_path: Path) -> str:
        try:
            return target_path.resolve().relative_to(self.backend_dir).as_posix()
        except ValueError:
            return str(target_path)


BACKEND_PATHS = BackendPaths()
