from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class WindowViewArtifacts:
    feature_frame: pd.DataFrame
    audit_frame: pd.DataFrame
    feature_metadata: dict[str, dict[str, Any]] = field(default_factory=dict)
    manifest_sections: dict[str, Any] = field(default_factory=dict)
    quality_sections: dict[str, Any] = field(default_factory=dict)
