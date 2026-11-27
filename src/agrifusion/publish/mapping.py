"""canonical rows -> contract records, and a Python port of the contract validator."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from agrifusion.settings.env import PROJECT_ROOT

SCHEMA_PATH = PROJECT_ROOT / "docs" / "contracts" / "result.schema.json"
TS_COLUMN = "record.ts_sample"
NODE_COLUMN = "record.node_id"


def load_schema(path: Path | None = None) -> dict[str, Any]:
    target = path or SCHEMA_PATH
    if not target.is_file():
        raise FileNotFoundError(
            f"Contract schema not found: {target} (run from a repository checkout or set AGRIFUSION_HOME)."
        )
    return json.loads(target.read_text(encoding="utf-8"))


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(value != value)  # NaN / pd.NA-safe enough for scalars
    except (TypeError, ValueError):
        return False


def _number(value: Any) -> float | int | None:
    if _is_missing(value) or isinstance(value, (bool, str)):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _flag_is_false(value: Any) -> bool:
    """True only when the flag is explicitly false. Unknown (None/NaN) keeps the value."""
    if _is_missing(value):
        return False
    return value is False or (hasattr(value, "item") and value.item() is False) or str(value).lower() == "false"


def _row_excluded(row: Any) -> bool:
    if _flag_is_true(row.get("record.is_demo")):
        return True
    reason = row.get("record.excluded_reason")
    return not _is_missing(reason) and str(reason).strip() != ""


def _flag_is_true(value: Any) -> bool:
    if _is_missing(value):
        return False
    return value is True or (hasattr(value, "item") and value.item() is True) or str(value).lower() == "true"


def _record_for(row: Any, group: dict[str, Any], ts: int) -> dict[str, Any] | None:
    group_flag = group.get("valid_flag")
    if group_flag and _flag_is_false(row.get(group_flag)):
        return None
    record: dict[str, Any] = {"ts": ts}
    for name, spec in group["fields"].items():
        flag = spec.get("valid_flag")
        if flag and _flag_is_false(row.get(flag)):
            continue
        value = _number(row.get(spec["source"]))
        if value is None:
            continue
        if spec.get("min") is not None and value < spec["min"]:
            continue
        if spec.get("max") is not None and value > spec["max"]:
            continue
        record[name] = value
    return record if len(record) > 1 else None


def build_groups(df: Any, schema: dict[str, Any]) -> tuple[dict[str, dict[int, dict[str, Any]]], str | None]:
    """Return ({group: {ts: record}}, node_id of the newest kept row).

    Deterministic: rows are ordered by (ts, record.id); a later row with the same ts replaces the earlier.
    """
    if TS_COLUMN not in df.columns:
        raise ValueError(f"canonical history has no {TS_COLUMN} column")
    ordering = [TS_COLUMN] + (["record.id"] if "record.id" in df.columns else [])
    ordered = df.sort_values(ordering, kind="mergesort")
    groups: dict[str, dict[int, dict[str, Any]]] = {g: {} for g in schema["groups"]}
    node_id: str | None = None
    for _, row in ordered.iterrows():
        if _row_excluded(row):
            continue
        ts_value = _number(row.get(TS_COLUMN))
        if ts_value is None or int(ts_value) != ts_value:
            continue
        ts = int(ts_value)
        used = False
        for group_id, group in schema["groups"].items():
            record = _record_for(row, group, ts)
            if record is not None:
                groups[group_id][ts] = record
                used = True
        if used and not _is_missing(row.get(NODE_COLUMN)):
            node_id = str(row.get(NODE_COLUMN))
    return groups, node_id


def validate_result(result: Any, schema: dict[str, Any]) -> list[str]:
    """Port of validateResult in Frontend/public/contract.js. Empty list = valid."""
    errors: list[str] = []
    is_int = lambda v: isinstance(v, int) and not isinstance(v, bool)  # noqa: E731
    is_num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)  # noqa: E731
    if not isinstance(result, dict):
        return ["result: not an object"]
    for key in result:
        if key not in ("meta", "latest", "history"):
            errors.append(f"result.{key}: not in contract")
    groups = schema["groups"]
    retention = schema["history_retention_seconds"]
    max_points = schema["history_max_points"]

    meta = result.get("meta")
    if not isinstance(meta, dict):
        errors.append("result.meta: missing")
    else:
        for name, spec in schema["meta"].items():
            if name not in meta:
                if spec["required"]:
                    errors.append(f"result.meta.{name}: missing")
                continue
            if spec["type"] == "int" and not is_int(meta[name]):
                errors.append(f"result.meta.{name}: expected int")
            if spec["type"] == "string" and not isinstance(meta[name], str):
                errors.append(f"result.meta.{name}: expected string")
        for key in meta:
            if key not in schema["meta"]:
                errors.append(f"result.meta.{key}: not in contract")
        if is_int(meta.get("schema_version")) and meta["schema_version"] != schema["schema_version"]:
            errors.append(f"result.meta.schema_version: expected {schema['schema_version']}")

    def check_record(path: str, group: str, record: Any, expected_key: str | None = None) -> None:
        if not isinstance(record, dict):
            errors.append(f"{path}: not an object")
            return
        if not is_int(record.get("ts")):
            errors.append(f"{path}.ts: expected int epoch seconds")
        elif expected_key is not None and str(record["ts"]) != expected_key:
            errors.append(f"{path}: key must equal String(ts)")
        fields = groups[group]["fields"]
        count = 0
        for name, value in record.items():
            if name == "ts":
                continue
            spec = fields.get(name)
            if spec is None:
                errors.append(f"{path}.{name}: not in contract")
                continue
            if not is_num(value):
                errors.append(f"{path}.{name}: expected finite number (omit the key instead of null)")
                continue
            count += 1
            if spec.get("min") is not None and value < spec["min"]:
                errors.append(f"{path}.{name}: below {spec['min']}")
            if spec.get("max") is not None and value > spec["max"]:
                errors.append(f"{path}.{name}: above {spec['max']}")
        if count == 0:
            errors.append(f"{path}: record has no value field (do not publish)")

    latest = result.get("latest")
    if not isinstance(latest, dict):
        errors.append("result.latest: missing")
    else:
        for group in latest:
            if group not in groups:
                errors.append(f"result.latest.{group}: not in contract")
            else:
                check_record(f"result.latest.{group}", group, latest[group])

    history = result.get("history")
    if not isinstance(history, dict):
        errors.append("result.history: missing")
    else:
        for group, records in history.items():
            if group not in groups:
                errors.append(f"result.history.{group}: not in contract")
                continue
            if len(records) > max_points:
                errors.append(f"result.history.{group}: {len(records)} points > {max_points}")
            stamps = [r["ts"] for r in records.values() if isinstance(r, dict) and is_int(r.get("ts"))]
            newest = max(stamps, default=0)
            for key, record in records.items():
                check_record(f"result.history.{group}.{key}", group, record, key)
                if isinstance(record, dict) and is_int(record.get("ts")) and newest - record["ts"] > retention:
                    errors.append(f"result.history.{group}.{key}: older than retention")
            if stamps and isinstance(latest, dict) and isinstance(latest.get(group), dict):
                if latest[group].get("ts") != newest:
                    errors.append(f"result.latest.{group}: ts differs from newest history record")
    return errors
