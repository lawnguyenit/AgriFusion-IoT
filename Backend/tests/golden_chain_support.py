"""Helpers for the Layer0 -> Layer1 golden test (see golden/data_chain/README.md).

Runs the real pipelines in-process on the synthetic JSON export, into a temp
backend dir, then writes a *normalized* snapshot of the outputs:
  - run-specific values removed (``*_utc`` keys, ``age_since_*``, temp paths),
  - parquet converted to CSV (rows sorted by ``record.id``, stable float format),
  - debug ``views/`` and the large ``source_snapshot.json`` (a copy of the input) skipped,
  - ``raw_history`` reduced to its (content-addressed) file names.
"""
from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path
from typing import Any

import pandas as pd

from agrifusion.settings.runtime import BackendSettings
from agrifusion.ingest import Layer0IngestionPipeline
from agrifusion.canonical import PreprocessingPipeline

GOLDEN_DIR = Path(__file__).resolve().parent / "golden" / "data_chain"
INPUT_EXPORT = GOLDEN_DIR / "input_export.json"
EXPECTED_DIR = GOLDEN_DIR / "expected"
NODE_ID = "Node2"

_VOLATILE_KEY = re.compile(r"(_utc$|^age_since_)")
_SKIP_PARTS = {"views", "archive_runs"}
_SKIP_FILES = {"source_snapshot.json"}


def run_chain(backend_dir: Path) -> BackendSettings:
    """Run Layer0 (json-export, full history) then Layer1 into ``backend_dir``."""
    settings = BackendSettings(
        project_root=backend_dir,
        source_type="json-export",
        input_json_path=INPUT_EXPORT,
        node_id=NODE_ID,
    )
    layer0 = Layer0IngestionPipeline(firebase_client=None, settings=settings).run(full_history=True)
    if layer0 is None:
        raise RuntimeError("Layer0 returned no result")
    layer1 = PreprocessingPipeline(settings).run()
    if layer1.status != "ok":
        raise RuntimeError(f"Layer1 status {layer1.status!r}")
    return settings


def _strip(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _strip(v) for k, v in value.items() if not _VOLATILE_KEY.search(k)}
    if isinstance(value, list):
        return [_strip(v) for v in value]
    return value


def _json_text(value: Any) -> str:
    return json.dumps(_strip(value), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _replace_paths(text: str, roots: list[Path]) -> str:
    for root, token in roots:
        for form in {str(root), root.as_posix(), json.dumps(str(root))[1:-1]}:
            text = text.replace(form, token)
    return text


def _parquet_to_csv(path: Path) -> str:
    frame = pd.read_parquet(path)
    frame = frame.sort_values("record.id", kind="stable").reset_index(drop=True)
    buffer = io.StringIO()
    frame.to_csv(buffer, index=False, float_format="%.10g", lineterminator="\n")
    return buffer.getvalue()


def _normalize_csv(text: str) -> str:
    # Re-emit through csv with LF endings so Windows/Linux checkouts compare equal.
    rows = list(csv.reader(io.StringIO(text)))
    buffer = io.StringIO()
    csv.writer(buffer, lineterminator="\n").writerows(rows)
    return buffer.getvalue()


def snapshot(backend_dir: Path) -> dict[str, str]:
    """Return {relative posix path: normalized text} for the outputs under backend_dir."""
    out_root = backend_dir / "output"
    roots = [(out_root, "<OUT>"), (INPUT_EXPORT.parent, "<INPUT_DIR>")]
    files: dict[str, str] = {}
    for path in sorted(out_root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(out_root)
        if _SKIP_PARTS.intersection(rel.parts) or path.name in _SKIP_FILES:
            continue
        key = rel.as_posix()
        if "raw_history" in rel.parts:
            files.setdefault("Layer0/Firebase_data/raw_history/INDEX.txt", "")
            files["Layer0/Firebase_data/raw_history/INDEX.txt"] += rel.relative_to(
                Path("Layer0/Firebase_data/raw_history")
            ).as_posix() + "\n"
            continue
        suffix = path.suffix.lower()
        if suffix == ".parquet":
            files[key[: -len(suffix)] + ".csv"] = _parquet_to_csv(path)
            continue
        text = _replace_paths(path.read_text(encoding="utf-8"), roots)
        if suffix == ".json":
            files[key] = _json_text(json.loads(text))
        elif suffix == ".jsonl":
            lines = [json.dumps(_strip(json.loads(line)), sort_keys=True, ensure_ascii=False)
                     for line in text.splitlines() if line.strip()]
            files[key] = "\n".join(lines) + ("\n" if lines else "")
        elif suffix == ".csv":
            files[key] = _normalize_csv(text)
        else:
            files[key] = text
    return dict(sorted(files.items()))


def write_expected(files: dict[str, str]) -> None:
    import shutil

    if EXPECTED_DIR.exists():
        shutil.rmtree(EXPECTED_DIR)
    for rel, text in files.items():
        target = EXPECTED_DIR / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")


def read_expected() -> dict[str, str]:
    files: dict[str, str] = {}
    for path in sorted(EXPECTED_DIR.rglob("*")):
        if path.is_file():
            files[path.relative_to(EXPECTED_DIR).as_posix()] = path.read_text(encoding="utf-8")
    return files
