"""External source schemas adapted into auditable candidate tables.

ADAPTERS maps DatasetProfile.intake_adapter to a function raw_dir -> (canonical, excluded,
audit, roles); roles are the column-role groups recorded in the intake manifest.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

import pandas as pd

from .stuard import build_stuard_candidate
from .uci import build_uci_candidate

AdapterResult = tuple[pd.DataFrame, pd.DataFrame, dict[str, object], dict[str, object]]


def _stuard(raw_dir: Path) -> AdapterResult:
    adapted = build_stuard_candidate(raw_dir)
    return adapted.canonical, adapted.excluded, adapted.audit, adapted.audit["feature_and_criterion_roles"]


def _uci(raw_dir: Path) -> AdapterResult:
    canonical, excluded, audit = build_uci_candidate(raw_dir / "air+quality.zip")
    return canonical, excluded, audit, audit["column_roles"]


ADAPTERS: dict[str, Callable[[Path], AdapterResult]] = {"stuard": _stuard, "uci": _uci}
