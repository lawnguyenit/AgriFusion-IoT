"""Contract and canonical input loading facades."""

from pathlib import Path

from Backend.Benchmark.weak_labels.infrastructure.io import load_canonical_history
from Backend.Benchmark.weak_labels.lifecycle.phase_c_native.pipeline import load_native_contract

__all__ = ["load_canonical_history", "load_native_contract"]


def resolve_contract_path(path: Path) -> Path:
    """Resolve a contract directory without selecting an implicit latest run."""

    resolved = path.resolve()
    if not resolved.is_dir():
        raise FileNotFoundError(f"Contract run directory does not exist: {resolved}")
    return resolved
