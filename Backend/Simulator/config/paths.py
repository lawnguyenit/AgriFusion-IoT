from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from Backend.Config.paths import BACKEND_PATHS


@dataclass(frozen=True)
class SimulatorPaths:
    backend_root: Path
    layer1_root: Path
    outputs_root: Path

    @classmethod
    def discover(cls) -> "SimulatorPaths":
        backend_root = BACKEND_PATHS.backend_dir
        return cls(
            backend_root=backend_root,
            layer1_root=backend_root / "Output_data" / "Layer1",
            outputs_root=backend_root / "Simulator" / "outputs",
        )
