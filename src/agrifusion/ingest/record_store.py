"""On-disk raw record store written by ingest and read by canonical.

This module is the ONLY place that knows the store format. ingest writes through
``RecordStoreWriter``; canonical reads through ``RecordStoreReader`` /
``read_latest`` and must not touch the files directly. The module imports only the
standard library, so importing it from canonical does not pull in sources, sync or
Firebase code (dependency direction: canonical -> ingest.record_store, never back).

Layout under ``<root>`` (``output/Layer0/Firebase_data``)::

    records/YYYY/MM/DD/<node_slug>_<event_key>_<sha256>.json
        one source record, verbatim: the JSON value exactly as received from
        Firebase or the JSON export, serialized with ``encode_record`` (sorted keys,
        2-space indent, UTF-8, trailing newline). ``sha256`` is the hash of the file
        bytes, so ``sha256sum`` of the file equals the name. Files are never
        overwritten: a second version of the same event gets its own file.
    records/index.json
        {date_key/event_key -> versions[]}; each version: sha256, file, source_kind
        ("telemetry" | "latest"), source_path. Sorted, no run timestamps, so the same
        sequence of inputs gives byte-identical index files.
    new_raw/latest.json
        the latest record, verbatim (same encoding).
    new_raw/latest_meta.json, sync_state.json, source_manifest.json, source_snapshot.json
        sync state / run metadata of the LAST run (may contain run times).
    runs/<run_id>.json
        one manifest per ingest run: times, source, date filter, counts.

Which version is "current" for an event: the last stored ``telemetry`` version (the
record at ``<node>/telemetry/<date>/<event>`` is the authoritative copy), else the
last stored version of any kind (only a ``latest/current`` copy was seen).
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

STORE_SCHEMA_VERSION = 1
RECORDS_DIRNAME = "records"
INDEX_FILENAME = "index.json"
RUNS_DIRNAME = "runs"
NEW_RAW_DIRNAME = "new_raw"
LATEST_FILENAME = "latest.json"
LATEST_META_FILENAME = "latest_meta.json"

SOURCE_KIND_TELEMETRY = "telemetry"
SOURCE_KIND_LATEST = "latest"
_SOURCE_KINDS = (SOURCE_KIND_TELEMETRY, SOURCE_KIND_LATEST)

_DATE_KEY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class RecordStoreError(ValueError):
    """The store on disk is inconsistent (hash mismatch, bad index)."""


def encode_record(record: Any) -> bytes:
    """Deterministic serialization of a source record (the bytes stored on disk)."""
    return (json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def record_sha256(record: Any) -> str:
    return hashlib.sha256(encode_record(record)).hexdigest()


def _safe_fragment(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._") or "event"


def _index_key(date_key: str, event_key: str) -> str:
    return f"{date_key}/{event_key}"


@dataclass(frozen=True)
class StoredRecord:
    """One current record as canonical sees it."""

    date_key: str
    event_key: str
    source_kind: str
    source_path: str
    sha256: str
    record: dict[str, Any]


@dataclass(frozen=True)
class PutResult:
    sha256: str
    path: Path
    new_file: bool
    new_version: bool


def _load_index(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": STORE_SCHEMA_VERSION, "records": {}}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("records"), dict):
        raise RecordStoreError(f"Malformed record index: {path}")
    if payload.get("schema_version") != STORE_SCHEMA_VERSION:
        raise RecordStoreError(
            f"Unsupported record index schema {payload.get('schema_version')!r} in {path}"
        )
    return payload


def _current_version(versions: list[dict[str, Any]]) -> dict[str, Any] | None:
    telemetry = [v for v in versions if v.get("source_kind") == SOURCE_KIND_TELEMETRY]
    if telemetry:
        return telemetry[-1]
    return versions[-1] if versions else None


class RecordStoreWriter:
    """Writes verbatim records + index. Call ``save_index()`` once at the end of a run."""

    def __init__(self, root: Path, *, node_slug: str):
        self.root = Path(root)
        self.records_root = self.root / RECORDS_DIRNAME
        self.index_path = self.records_root / INDEX_FILENAME
        self.node_slug = node_slug
        self._index = _load_index(self.index_path)

    def put(
        self,
        *,
        date_key: str,
        event_key: str,
        source_kind: str,
        source_path: str,
        record: dict[str, Any],
    ) -> PutResult:
        if source_kind not in _SOURCE_KINDS:
            raise ValueError(f"source_kind must be one of {_SOURCE_KINDS}, got {source_kind!r}")
        if not _DATE_KEY.match(str(date_key)):
            raise ValueError(f"date_key must be YYYY-MM-DD, got {date_key!r}")
        data = encode_record(record)
        digest = hashlib.sha256(data).hexdigest()
        year, month, day = str(date_key).split("-")
        rel = Path(RECORDS_DIRNAME, year, month, day, f"{self.node_slug}_{_safe_fragment(str(event_key))}_{digest}.json")
        path = self.root / rel

        new_file = False
        if path.exists():
            existing = path.read_bytes()
            if hashlib.sha256(existing).hexdigest() != digest:
                raise RecordStoreError(f"Content-addressed record collision (file changed on disk): {path}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as handle:
                handle.write(data)
            new_file = True

        entry = self._index["records"].setdefault(
            _index_key(str(date_key), str(event_key)),
            {"date_key": str(date_key), "event_key": str(event_key), "versions": []},
        )
        version = {
            "file": rel.as_posix(),
            "sha256": digest,
            "source_kind": source_kind,
            "source_path": str(source_path),
        }
        new_version = version not in entry["versions"]
        if new_version:
            entry["versions"].append(version)
        return PutResult(sha256=digest, path=path, new_file=new_file, new_version=new_version)

    def save_index(self) -> Path:
        records = dict(sorted(self._index["records"].items()))
        payload = {"schema_version": STORE_SCHEMA_VERSION, "records": records}
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        if not self.index_path.exists() or self.index_path.read_text(encoding="utf-8") != text:
            self.index_path.write_text(text, encoding="utf-8", newline="\n")
        return self.index_path


def write_latest_record(root: Path, record: dict[str, Any]) -> Path:
    path = Path(root) / NEW_RAW_DIRNAME / LATEST_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encode_record(record))
    return path


def write_run_manifest(root: Path, run_id: str, payload: dict[str, Any]) -> Path:
    runs = Path(root) / RUNS_DIRNAME
    runs.mkdir(parents=True, exist_ok=True)
    path = runs / f"{run_id}.json"
    suffix = 1
    while path.exists():
        path = runs / f"{run_id}_{suffix}.json"
        suffix += 1
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return path


class RecordStoreReader:
    """Read-only view used by canonical."""

    def __init__(self, root: Path, *, verify: bool = True):
        self.root = Path(root)
        self.index_path = self.root / RECORDS_DIRNAME / INDEX_FILENAME
        self.verify = verify

    def exists(self) -> bool:
        return self.index_path.exists()

    def iter_current(self) -> Iterator[StoredRecord]:
        """Yield the current version of every event, sorted by (date_key, event_key)."""
        if not self.index_path.exists():
            return
        index = _load_index(self.index_path)
        for key in sorted(index["records"]):
            entry = index["records"][key]
            version = _current_version(entry.get("versions") or [])
            if version is None:
                continue
            data = (self.root / version["file"]).read_bytes()
            if self.verify and hashlib.sha256(data).hexdigest() != version["sha256"]:
                raise RecordStoreError(f"Record file does not match its hash: {version['file']}")
            record = json.loads(data.decode("utf-8"))
            if not isinstance(record, dict):
                continue
            yield StoredRecord(
                date_key=str(entry["date_key"]),
                event_key=str(entry["event_key"]),
                source_kind=str(version["source_kind"]),
                source_path=str(version["source_path"]),
                sha256=str(version["sha256"]),
                record=record,
            )


def read_latest(root: Path) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Return (latest record verbatim, latest_meta) from ``new_raw/``; None when absent."""
    new_raw = Path(root) / NEW_RAW_DIRNAME
    out: list[dict[str, Any] | None] = []
    for name in (LATEST_FILENAME, LATEST_META_FILENAME):
        path = new_raw / name
        if not path.exists():
            out.append(None)
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        out.append(payload if isinstance(payload, dict) else None)
    return out[0], out[1]
