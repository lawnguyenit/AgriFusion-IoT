from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


def ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def ensure_parent(path: Path) -> None:
    ensure_directory(path.parent)


def atomic_write_bytes(path: Path, payload: bytes) -> None:
    ensure_parent(path)
    temp_path = path.with_name(f".{path.name}.tmp")
    temp_path.write_bytes(payload)
    temp_path.replace(path)


def serialize_json(payload: Any) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if isinstance(payload, dict):
                rows.append(payload)  # type: ignore[arg-type]
    return rows


def write_json(path: Path, payload: Any) -> None:
    atomic_write_bytes(path, serialize_json(payload))


def append_jsonl(path: Path, rows: Iterable[dict[str, Any]] | dict[str, Any]) -> int:
    buffered_rows = list(rows) if not isinstance(rows, dict) else [rows]
    if not buffered_rows:
        return 0

    ensure_parent(path)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        for row in buffered_rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")
    return len(buffered_rows)


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    buffered_rows = list(rows)
    ensure_parent(path)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in buffered_rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")
    return len(buffered_rows)


def gzip_file(path: Path) -> Path:
    gz_path = path.with_suffix(path.suffix + ".gz")
    return gzip_file_to(path, gz_path)


def gzip_file_to(path: Path, gz_path: Path) -> Path:
    ensure_parent(gz_path)
    temp_gz_path = gz_path.with_name(f".{gz_path.name}.tmp")

    with path.open("rb") as source, gzip.open(temp_gz_path, "wb") as target:
        target.write(source.read())

    temp_gz_path.replace(gz_path)
    path.unlink()
    return gz_path
