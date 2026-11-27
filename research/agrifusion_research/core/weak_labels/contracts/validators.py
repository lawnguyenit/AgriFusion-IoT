"""Small structural validators shared by lifecycle entry points."""

from pathlib import Path


def validate_contract_namespace(path: Path, *, required_files: tuple[str, ...] = ()) -> Path:
    resolved = path.resolve()
    if not resolved.is_dir():
        raise FileNotFoundError(f"Contract directory does not exist: {resolved}")
    missing = [name for name in required_files if not (resolved / name).exists()]
    if missing:
        raise ValueError(f"Contract directory is incomplete; missing: {missing}")
    return resolved
