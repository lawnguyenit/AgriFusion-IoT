from __future__ import annotations

from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def backend_env_path() -> Path:
    return repo_root() / "Backend" / "Services" / ".env"


def parse_dotenv(dotenv_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}

    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]

        values[key] = value

    return values


def load_backend_env() -> tuple[Path, dict[str, str]]:
    dotenv_path = backend_env_path()
    if not dotenv_path.exists():
        raise FileNotFoundError(f"Backend env not found: {dotenv_path}")

    return dotenv_path, parse_dotenv(dotenv_path)
