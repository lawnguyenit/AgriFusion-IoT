from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

SERVICES_DIR = Path(__file__).resolve().parents[1]
load_dotenv(dotenv_path=SERVICES_DIR / ".env", override=False)


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
