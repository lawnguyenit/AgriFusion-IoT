from __future__ import annotations

import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
import json

ROOT_DIR = Path(__file__).resolve().parents[4]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


RUN_DIR_PATTERN = re.compile(r"^(?P<prefix>.+)_(?P<date>\d{8})_(?P<time>\d{6})$")


@dataclass(frozen=True)
class MigrationResult:
    root: Path
    moved: int
    skipped: int


def migrate_root(output_root: Path) -> MigrationResult:
    output_root = output_root.resolve()
    if not output_root.exists():
        return MigrationResult(root=output_root, moved=0, skipped=0)

    moved = 0
    skipped = 0
    for entry in sorted(output_root.iterdir()):
        if not entry.is_dir():
            continue
        if re.fullmatch(r"\d{2}-\d{2}-\d{4}", entry.name):
            skipped += 1
            continue
        match = RUN_DIR_PATTERN.fullmatch(entry.name)
        if match is None:
            skipped += 1
            continue
        date_folder = _format_date_bucket(match.group("date"))
        run_leaf = f"{match.group('prefix')}_{match.group('time')}"
        target_dir = output_root / date_folder / run_leaf
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        if target_dir.exists():
            skipped += 1
            continue
        shutil.move(str(entry), str(target_dir))
        _rewrite_moved_paths(root=output_root, run_id=match.group(0), new_run_dir=target_dir)
        moved += 1
    return MigrationResult(root=output_root, moved=moved, skipped=skipped)


def _format_date_bucket(yyyymmdd: str) -> str:
    if len(yyyymmdd) != 8:
        raise ValueError(f"Invalid date token: {yyyymmdd}")
    return f"{yyyymmdd[6:8]}-{yyyymmdd[4:6]}-{yyyymmdd[0:4]}"


def _rewrite_moved_paths(*, root: Path, run_id: str, new_run_dir: Path) -> None:
    old_run_dir = root / run_id
    old_text = str(old_run_dir)
    new_text = str(new_run_dir)
    text_exts = {".json", ".yaml", ".yml", ".txt", ".csv"}
    json_files = {"pretrain_report.json", "training_report.json", "run_status.json", "run_config.json"}

    for file_path in new_run_dir.rglob("*"):
        if not file_path.is_file() or file_path.suffix.lower() not in text_exts:
            continue
        if file_path.name in json_files:
            try:
                payload = json.loads(file_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            updated = _replace_paths(payload, old_text, new_text)
            if updated != payload:
                file_path.write_text(json.dumps(updated, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            continue
        try:
            text = file_path.read_text(encoding="utf-8")
        except Exception:
            continue
        if old_text in text:
            file_path.write_text(text.replace(old_text, new_text), encoding="utf-8")


def _replace_paths(value: object, old_text: str, new_text: str) -> object:
    if isinstance(value, dict):
        return {key: _replace_paths(inner_value, old_text, new_text) for key, inner_value in value.items()}
    if isinstance(value, list):
        return [_replace_paths(item, old_text, new_text) for item in value]
    if isinstance(value, str):
        if value == old_text:
            return new_text
        if value.startswith(old_text):
            return new_text + value[len(old_text) :]
    return value


def main() -> None:
    roots = [
        ROOT_DIR / "Backend" / "Benchmark" / "pretrain_supervised" / "pretrain" / "outputs",
        ROOT_DIR / "Backend" / "Benchmark" / "pretrain_supervised" / "v1" / "outputs",
        ROOT_DIR / "Backend" / "Benchmark" / "pretrain_supervised" / "v2" / "outputs",
    ]
    results = [migrate_root(root) for root in roots]
    for result in results:
        print(f"{result.root}: moved={result.moved}, skipped={result.skipped}")


if __name__ == "__main__":
    main()
