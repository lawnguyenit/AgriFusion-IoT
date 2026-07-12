from __future__ import annotations

import math
from typing import Any

import pandas as pd

from ...utils.common import safe_int


def first_not_none(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def first_non_empty_str(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    if isinstance(value, (int, float)) and value in {0, 1}:
        return bool(int(value))
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"true", "1", "yes"}:
            return True
        if text in {"false", "0", "no"}:
            return False
    return None


def first_bool(*values: Any) -> bool | None:
    for value in values:
        normalized = as_optional_bool(value)
        if normalized is not None:
            return normalized
    return None


def normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    return text or None


def normalize_error_code(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and float(value) == 0.0:
        return "ok"
    text = str(value).strip().lower()
    if not text or text == "0":
        return "ok"
    if text == "ok":
        return "ok"
    return text


def normalize_buffer_reason(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    mapping = {
        "publish_blocked_transport_not_ready": "transport_not_ready",
        "publish_blocked_begin_not_done": "transport_not_ready",
        "publish_blocked_auth_not_initialized": "transport_not_ready",
        "publish_blocked_gate_not_ready": "transport_not_ready",
        "network_down": "network_down",
        "firebase_write_fail": "http_action_fail",
        "firebase_get_fail": "http_action_fail",
        "publish_error": "http_action_fail",
        "offline": "other",
    }
    return mapping.get(normalized, normalized or "unknown")


def derive_protocol_fault(flags: tuple[bool | None, ...]) -> bool | None:
    if any(flag is False for flag in flags):
        return True
    if all(flag is True for flag in flags):
        return False
    return None


def tri_or(left: bool | None, right: bool | None) -> bool | None:
    if left is True or right is True:
        return True
    if left is False and right is False:
        return False
    return None


def as_int_from_pd(value: Any) -> int | None:
    if pd.isna(value):
        return None
    return safe_int(value)


def json_safe_value(value: Any) -> Any:
    if isinstance(value, float) and math.isnan(value):
        return None
    if pd.isna(value):
        return None
    return value


def nest_row_by_namespace(row: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "record": {},
        "sht": {},
        "npk": {},
        "delivery": {},
        "network": {},
        "device": {},
        "sensor": {},
    }
    for key, value in row.items():
        if "." not in key:
            continue
        namespace, field_name = key.split(".", 1)
        bucket = result.setdefault(namespace, {})
        bucket[field_name] = json_safe_value(value)
    return result
