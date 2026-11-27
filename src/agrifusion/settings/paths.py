from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .env import PROJECT_ROOT


@dataclass(frozen=True)
class BackendPaths:
    """Well-known locations under the project root."""

    project_root: Path = field(default_factory=lambda: PROJECT_ROOT.resolve())

    @property
    def backend_dir(self) -> Path:
        """Legacy ``Backend/`` folder; only tests and the deprecated ``Backend.main`` shim remain."""
        return self.project_root / "Backend"

    @property
    def output_dir(self) -> Path:
        """Generated artifacts (gitignored)."""
        return self.project_root / "output"

    @property
    def layer0_dir(self) -> Path:
        return self.output_dir / "Layer0"

    @property
    def layer1_dir(self) -> Path:
        return self.output_dir / "Layer1"

    def ensure_directory(self, path: Path) -> Path:
        path.mkdir(parents=True, exist_ok=True)
        return path


BACKEND_PATHS = BackendPaths()
