from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ArtifactRef:
    role: str
    path: str
    format: str
    description: str
