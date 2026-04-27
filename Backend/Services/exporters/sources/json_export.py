from __future__ import annotations

import json
from pathlib import Path

try:
    from Services.config.settings import ExportSettings
except ModuleNotFoundError:
    from ...config.settings import ExportSettings

from ..utils.file_store import sha256_hex
from .base import NormalizedSnapshotMixin


class JsonExportSourceAdapter(NormalizedSnapshotMixin):
    source_type = "json-export"
    skip_duplicate_on_same_source = True

    def __init__(self, settings: ExportSettings):
        super().__init__(settings)
        if settings.input_json_path is None:
            raise ValueError("--input-json is required when --source json-export")

        self.input_path = Path(settings.input_json_path)
        self.source_uri = str(self.input_path)

    def _ensure_prepared(self) -> None:
        if self._source_payload is not None:
            return

        if not self.input_path.exists():
            raise FileNotFoundError(f"JSON export file not found: {self.input_path}")

        raw_bytes = self.input_path.read_bytes()
        payload = json.loads(raw_bytes.decode("utf-8"))
        self._set_snapshot_payload(payload=payload, source_sha256=sha256_hex(raw_bytes))
