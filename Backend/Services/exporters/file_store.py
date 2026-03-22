import gzip
import hashlib
import json
from pathlib import Path
from typing import Any


def ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def atomic_write_bytes(path: Path, payload: bytes) -> None:
    ensure_directory(path.parent)
    temp_path = path.with_name(f".{path.name}.tmp")
    temp_path.write_bytes(payload)
    temp_path.replace(path)


def serialize_json(payload: Any) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def write_json(path: Path, payload: Any) -> None:
    atomic_write_bytes(path, serialize_json(payload))


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def append_jsonl(path: Path, payload: Any) -> None:
    ensure_directory(path.parent)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        handle.write("\n")


def gzip_file(path: Path) -> Path:
    gz_path = path.with_suffix(path.suffix + ".gz")

    with path.open("rb") as source, gzip.open(gz_path, "wb") as target:
        target.write(source.read())

    path.unlink()
    return gz_path


def gzip_file_to(path: Path, gz_path: Path) -> Path:
    ensure_directory(gz_path.parent)
    temp_gz_path = gz_path.with_name(f".{gz_path.name}.tmp")

    with path.open("rb") as source, gzip.open(temp_gz_path, "wb") as target:
        target.write(source.read())

    temp_gz_path.replace(gz_path)
    path.unlink()
    return gz_path
