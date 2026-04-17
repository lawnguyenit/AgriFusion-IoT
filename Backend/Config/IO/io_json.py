from email.policy import default
import json
from pathlib import Path
from typing import Any, Iterable


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


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
    _ensure_parent(path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    buffered_rows = list(rows)
    if not buffered_rows:
        return 0

    _ensure_parent(path)
    with path.open("a", encoding="utf-8") as handle:
        for row in buffered_rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")
    return len(buffered_rows)


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    buffered_rows = list(rows)
    _ensure_parent(path)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in buffered_rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")
    return len(buffered_rows)

def get_attribute_jsonl(path: Path, attribute: list[str]) -> Any:
    data_list = read_jsonl(path)
    if not data_list or not isinstance(data_list, list[dict[str, Any]]):
        print(f"Lỗi: Không thể đọc list từ {path}")
        return None
    lenAttribute = len(data_list[0].get(attribute)) 
    data_list[0].get(attribute[0])
    return data_list[0].get(attribute[1]) if data_list else None