import re
from datetime import datetime
from typing import Any


DATE_KEY_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIMESTAMP_KEY_PATTERN = re.compile(r"^(?P<ts>\d{8,})(?:[_-](?P<suffix>.+))?$")
INTEGER_KEY_PATTERN = re.compile(r"^\d+$")


def canonicalize_json(data: Any) -> Any:
    if isinstance(data, dict):
        ordered_items = sorted(data.items(), key=lambda item: _sort_key(item[0]))
        return {str(key): canonicalize_json(value) for key, value in ordered_items}

    if isinstance(data, list):
        return [canonicalize_json(item) for item in data]

    return data


def _sort_key(raw_key: Any) -> tuple[int, Any, str]:
    key = str(raw_key)

    if DATE_KEY_PATTERN.match(key):
        parsed_date = datetime.strptime(key, "%Y-%m-%d").date()
        return (0, parsed_date.toordinal(), key)

    timestamp_match = TIMESTAMP_KEY_PATTERN.match(key)
    if timestamp_match:
        ts_part = int(timestamp_match.group("ts"))
        suffix = timestamp_match.group("suffix") or ""
        return (1, ts_part, suffix)

    if INTEGER_KEY_PATTERN.match(key):
        return (2, int(key), key)

    return (3, key, key)
