from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from Services.config.settings import ExportSettings
except ModuleNotFoundError:
    from ...config.settings import ExportSettings

from ..utils.file_store import write_json


def write_latest_meta(settings: ExportSettings, payload: dict[str, Any]) -> Path:
    write_json(settings.latest_meta_local_path, payload)
    return settings.latest_meta_local_path


def write_latest_payload(settings: ExportSettings, payload: dict[str, Any]) -> Path:
    write_json(settings.latest_payload_path, payload)
    return settings.latest_payload_path


def write_source_audit_artifacts(
    settings: ExportSettings,
    manifest_payload: dict[str, Any],
    snapshot_payload: dict[str, Any] | None = None,
) -> tuple[Path, Path | None]:
    write_json(settings.source_manifest_path, manifest_payload)

    snapshot_path: Path | None = None
    if snapshot_payload is not None:
        write_json(settings.source_snapshot_path, snapshot_payload)
        snapshot_path = settings.source_snapshot_path

    return settings.source_manifest_path, snapshot_path


def base_source_manifest_payload(
    *,
    source_type: str,
    source_uri: str,
    source_sha256: str | None,
    checked_at: datetime,
    node_id: str | None,
    node_slug: str | None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "source_type": source_type,
        "source_uri": source_uri,
        "source_sha256": source_sha256,
        "imported_at_utc": checked_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "configured_node_id": node_id,
        "configured_node_slug": node_slug,
    }
