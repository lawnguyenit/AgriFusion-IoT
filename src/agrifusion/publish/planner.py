"""Desired result tree + minimal multi-path update (retention, idempotency)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .mapping import validate_result


@dataclass
class PublishPlan:
    tree: dict[str, Any]  # desired final state of result/*
    updates: dict[str, Any]  # flat multi-path update; None = delete
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def empty(self) -> bool:
        return not self.updates


def trim(records: dict[int, dict[str, Any]], retention: int, max_points: int) -> dict[int, dict[str, Any]]:
    """Deterministic: drop ts < newest - retention, then keep the newest `max_points`."""
    if not records:
        return {}
    newest = max(records)
    kept = sorted(ts for ts in records if newest - ts <= retention)
    kept = kept[-max_points:]
    return {ts: records[ts] for ts in kept}


def _remote_group(remote: Any, group: str) -> dict[int, dict[str, Any]]:
    node = ((remote or {}).get("history") or {}).get(group) or {}
    out: dict[int, dict[str, Any]] = {}
    if not isinstance(node, dict):
        return out
    for key, record in node.items():
        if isinstance(record, dict) and str(key).isdigit():
            out[int(key)] = record
    return out


def build_plan(
    groups: dict[str, dict[int, dict[str, Any]]],
    *,
    schema: dict[str, Any],
    node_id: str,
    source: str,
    now_ts: int,
    remote: dict[str, Any] | None = None,
    result_path: str = "result",
    heartbeat: bool = False,
) -> PublishPlan:
    """`remote` is the current `result` subtree (or None = assume empty).

    Remote records not in canonical are kept while inside retention (canonical wins on equal ts).
    """
    retention = schema["history_retention_seconds"]
    max_points = schema["history_max_points"]
    final: dict[str, dict[int, dict[str, Any]]] = {}
    for group in schema["groups"]:
        merged = {**_remote_group(remote, group), **groups.get(group, {})}
        final[group] = trim(merged, retention, max_points)

    tree: dict[str, Any] = {"latest": {}, "history": {}}
    stamps = []
    for group, records in final.items():
        if not records:
            continue
        tree["history"][group] = {str(ts): records[ts] for ts in sorted(records)}
        tree["latest"][group] = records[max(records)]
        stamps.append(max(records))
    if not stamps:
        raise ValueError("no publishable records (all rows excluded, invalid or empty)")
    meta: dict[str, Any] = {
        "schema_version": schema["schema_version"],
        "published_ts": int(now_ts),
        "latest_sample_ts": max(stamps),
        "node_id": node_id,
        "source": source,
    }
    tree = {"meta": meta, **tree}
    errors = validate_result(tree, schema)
    if errors:
        raise ValueError("planned tree violates the contract:\n" + "\n".join(errors[:20]))

    base = result_path.strip("/")
    remote = remote or {}
    updates: dict[str, Any] = {}
    counts = {"written": 0, "deleted": 0}
    for group in tree["history"]:
        old = _remote_group(remote, group)
        new = final[group]
        for ts in sorted(new):
            if old.get(ts) != new[ts]:
                updates[f"{base}/history/{group}/{ts}"] = new[ts]
                counts["written"] += 1
        for ts in sorted(set(old) - set(new)):
            updates[f"{base}/history/{group}/{ts}"] = None
            counts["deleted"] += 1
        if (remote.get("latest") or {}).get(group) != tree["latest"][group]:
            updates[f"{base}/latest/{group}"] = tree["latest"][group]
    old_meta = remote.get("meta") or {}
    meta_changed = {k: v for k, v in meta.items() if k != "published_ts"} != {
        k: v for k, v in old_meta.items() if k != "published_ts"
    }
    if updates or meta_changed or heartbeat:
        updates[f"{base}/meta"] = meta
    return PublishPlan(tree=tree, updates=updates, counts=counts)
