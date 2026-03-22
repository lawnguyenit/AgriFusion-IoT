import re
from typing import Any


DATE_KEY_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def extract_path(payload: Any, firebase_path: str) -> Any:
    clean_path = firebase_path.strip("/")
    if not clean_path:
        return payload

    current = payload
    for segment in clean_path.split("/"):
        if not isinstance(current, dict):
            return None
        current = current.get(segment)
        if current is None:
            return None

    return current


def count_records(payload: Any) -> int:
    if isinstance(payload, list):
        return len(payload)

    if isinstance(payload, dict):
        if all(
            isinstance(key, str) and DATE_KEY_PATTERN.match(key) and isinstance(value, dict)
            for key, value in payload.items()
        ):
            return sum(len(value) for value in payload.values())

        return len(payload)

    return int(payload is not None)
