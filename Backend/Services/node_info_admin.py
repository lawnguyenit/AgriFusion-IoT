from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from Config.runtime import BackendSettings
except ModuleNotFoundError:
    from ..Config.runtime import BackendSettings


REQUIRED_INFO_SECTIONS = (
    "identity",
    "deployment",
    "hardware",
    "sensors_registry",
    "firmware_current",
    "config_current",
    "calibration_current",
)


def load_node_info_json(path: str | Path) -> dict[str, Any]:
    source_path = Path(path).resolve()
    with source_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("Node info JSON must be a top-level object")
    return payload


def prepare_node_info_payload(
    *,
    payload: dict[str, Any],
    settings: BackendSettings,
    updated_by: str | None,
) -> dict[str, Any]:
    normalized = dict(payload)
    schema_version = normalized.get("schema_version")
    if schema_version != 2:
        raise ValueError(f"Node info schema_version must be 2, got: {schema_version!r}")

    for section in REQUIRED_INFO_SECTIONS:
        if not isinstance(normalized.get(section), dict):
            raise ValueError(f"Node info section '{section}' must be a JSON object")

    identity = normalized["identity"]
    node_id = str(identity.get("node_id") or "").strip()
    if not node_id:
        raise ValueError("Node info identity.node_id is required")
    if node_id != settings.node_id:
        raise ValueError(f"Node info identity.node_id='{node_id}' does not match runtime node '{settings.node_id}'")

    if not isinstance(normalized["sensors_registry"], dict) or not normalized["sensors_registry"]:
        raise ValueError("Node info sensors_registry must contain at least one registered sensor")

    effective_updated_by = str(updated_by or normalized.get("updated_by") or "").strip()
    if not effective_updated_by:
        raise ValueError("Node info requires updated_by, either in JSON or via --info-updated-by")

    normalized["info_version"] = int(normalized.get("info_version") or 1)
    normalized["updated_at"] = str(
        normalized.get("updated_at") or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    normalized["updated_by"] = effective_updated_by
    return normalized


def write_node_info(
    *,
    firebase_client: Any,
    settings: BackendSettings,
    payload: dict[str, Any],
) -> bool:
    return bool(firebase_client.set_data(settings.info_root_path, payload))
