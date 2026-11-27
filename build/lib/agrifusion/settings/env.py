from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


def _find_project_root() -> Path:
    """Directory that holds ``output/`` and ``.env``.

    ``AGRIFUSION_HOME`` wins. Otherwise, in a source checkout (this file lives in
    ``<root>/src/agrifusion/settings``) it is the repository root. For an installed copy
    it falls back to the current working directory.
    """
    home = os.getenv("AGRIFUSION_HOME")
    if home:
        return Path(home).expanduser().resolve()
    candidate = Path(__file__).resolve().parents[3]
    if (candidate / "pyproject.toml").is_file() and (candidate / "src" / "agrifusion").is_dir():
        return candidate
    return Path.cwd().resolve()


PROJECT_ROOT = _find_project_root()

# `<root>/.env` first; `<root>/Backend/.env` is the legacy location and still honoured.
# override=False: real environment variables always win, and the first file wins over the second.
load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=False)
load_dotenv(dotenv_path=PROJECT_ROOT / "Backend" / ".env", override=False)


def env_str(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None:
        return default
    value = value.strip()
    return value or default


def env_int(name: str, default: int) -> int:
    value = env_str(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def env_path(name: str) -> Path | None:
    value = env_str(name)
    if value is None:
        return None
    return Path(value).expanduser()


def coerce_optional_path(value: object) -> Path | None:
    if value is None:
        return None
    if isinstance(value, Path):
        return value.expanduser()
    return Path(str(value)).expanduser()
