from __future__ import annotations

import math
import re
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
    if not normalized:
        return None

    direct_mapping = {
        "publish_blocked_transport_not_ready": "transport_not_ready",
        "publish_blocked_begin_not_done": "transport_not_ready",
        "publish_blocked_auth_not_initialized": "auth_not_initialized",
        "publish_blocked_gate_not_ready": "transport_not_ready",
        "transport_not_ready": "transport_not_ready",
        "network_down": "network_down",
        "firebase_write_fail": "http_action_fail",
        "firebase_get_fail": "http_action_fail",
        "publish_error": "http_action_fail",
        "http_action_fail": "http_action_fail",
        "auth_not_initialized": "auth_not_initialized",
        "sim_not_ready": "sim_not_ready",
        "modem_not_ready": "modem_not_ready",
        "offline": "other",
    }
    if normalized in direct_mapping:
        return direct_mapping[normalized]

    token_candidates = _buffer_reason_tokens(normalized)
    token_set = set(token_candidates)

    if _contains_buffer_reason_token(
        token_set,
        {"http_action_fail", "firebase_write_fail", "firebase_get_fail", "publish_error"},
    ):
        return "http_action_fail"
    if _contains_buffer_reason_token(
        token_set,
        {"auth_not_initialized", "publish_blocked_auth_not_initialized"},
    ):
        return "auth_not_initialized"
    if _contains_buffer_reason_token(
        token_set,
        {"network_down", "network_lost", "network_error", "pdp_inactive"},
    ):
        return "network_down"
    if _contains_buffer_reason_token(
        token_set,
        {"sim_not_ready", "cpin:not ready", "cpin: not ready", "no_sim", "sim_missing"},
    ):
        return "sim_not_ready"
    if _contains_buffer_reason_token(
        token_set,
        {"modem_not_ready", "atready:0", "atready: 0"},
    ):
        return "modem_not_ready"
    if _contains_buffer_reason_token(
        token_set,
        {
            "transport_not_ready",
            "publish_blocked_transport_not_ready",
            "publish_blocked_begin_not_done",
            "publish_blocked_gate_not_ready",
            "begin_not_done",
            "gate_not_ready",
        },
    ):
        return "transport_not_ready"
    return "other"


def _buffer_reason_tokens(normalized: str) -> list[str]:
    tail = normalized.split("->", 1)[-1].strip() if "->" in normalized else normalized
    raw_tokens = re.split(r"[|\n\r\t,]+", tail)
    tokens: list[str] = []
    for raw_token in raw_tokens:
        token = re.sub(r"\s+", " ", raw_token).strip(" -")
        if not token:
            continue
        tokens.append(token)
        tokens.extend(token.split())
        if ":" in token:
            key, value = token.split(":", 1)
            key = key.strip()
            value = value.strip()
            if key:
                tokens.append(key)
                tokens.append(f"{key}:{value}")
    return tokens


def _contains_buffer_reason_token(token_set: set[str], patterns: set[str]) -> bool:
    for token in token_set:
        if token in patterns:
            return True
        if any(pattern in token for pattern in patterns):
            return True
    return False


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
