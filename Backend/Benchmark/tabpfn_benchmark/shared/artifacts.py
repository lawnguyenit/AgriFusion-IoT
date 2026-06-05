from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


def create_run_directory(output_root: Path, prefix: str) -> tuple[str, Path]:
    output_root.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    run_id = f"{prefix}_{now.strftime('%Y%m%d_%H%M%S')}"
    output_dir = output_root / run_id
    output_dir.mkdir(parents=True, exist_ok=False)
    return run_id, output_dir


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_yaml(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_to_yaml(payload).rstrip() + "\n", encoding="utf-8")


def _to_yaml(payload: object, indent: int = 0) -> str:
    prefix = " " * indent
    if isinstance(payload, dict):
        lines: list[str] = []
        for key, value in payload.items():
            if isinstance(value, (dict, list)):
                lines.append(f"{prefix}{key}:")
                lines.append(_to_yaml(value, indent + 2))
            else:
                lines.append(f"{prefix}{key}: {_yaml_scalar(value)}")
        return "\n".join(lines)
    if isinstance(payload, list):
        lines: list[str] = []
        for value in payload:
            if isinstance(value, (dict, list)):
                lines.append(f"{prefix}-")
                lines.append(_to_yaml(value, indent + 2))
            else:
                lines.append(f"{prefix}- {_yaml_scalar(value)}")
        return "\n".join(lines)
    return f"{prefix}{_yaml_scalar(payload)}"


def _yaml_scalar(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    escaped = text.replace("\\", "\\\\").replace("\"", "\\\"")
    return f"\"{escaped}\""
