"""`agrifusion publish` implementation (called from agrifusion.cli)."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from agrifusion.io.storage import read_table, write_json
from agrifusion.settings.runtime import BackendSettings

from .mapping import build_groups, load_schema
from .planner import build_plan

DEFAULT_SOURCE = "agrifusion-backend"


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="agrifusion publish", description="Publish canonical data to RTDB result/*.")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Print the planned update, write nothing (default).")
    mode.add_argument("--apply", action="store_true", help="Perform the multi-path update.")
    p.add_argument("--input", help="Canonical history file (.parquet). Default: Layer1 canonical/telemetry_history.parquet.")
    p.add_argument("--out", help="Write the planned result tree to this JSON file.")
    p.add_argument("--node-id", help="meta.node_id; default: record.node_id of the newest published row.")
    p.add_argument("--source", default=DEFAULT_SOURCE, help="meta.source.")
    p.add_argument("--result-path", default="result", help="RTDB root of the contract.")
    p.add_argument("--remote-diff", action="store_true", help="Read RTDB (dry-run too) and plan only the difference. Implied by --apply.")
    p.add_argument("--heartbeat", action="store_true", help="Always rewrite meta (refresh published_ts) even when nothing changed.")
    return p.parse_args(argv)


def run(argv: list[str], client: Any | None = None, now_ts: int | None = None) -> int:
    args = parse_args(argv)
    schema = load_schema()
    path = Path(args.input) if args.input else BackendSettings().layer1_root / "canonical" / "telemetry_history.parquet"
    if not path.is_file():
        print(f"Canonical history not found: {path}")
        return 1
    groups, detected_node = build_groups(read_table(path), schema)
    node_id = args.node_id or detected_node
    if not node_id:
        print("node id unknown: pass --node-id")
        return 1

    remote = None
    if args.apply or args.remote_diff:
        if client is None:
            from agrifusion.cloud import FirebaseRTDBClient

            client = FirebaseRTDBClient()
        remote = client.read(args.result_path)

    try:
        plan = build_plan(
            groups, schema=schema, node_id=node_id, source=args.source,
            now_ts=int(time.time()) if now_ts is None else now_ts,
            remote=remote, result_path=args.result_path, heartbeat=args.heartbeat,
        )
    except ValueError as exc:
        print(f"Not publishing: {exc}")
        return 1

    if args.out:
        write_json(Path(args.out), plan.tree)
    print(json.dumps(plan.updates, ensure_ascii=False, indent=2, sort_keys=True))
    print(f"paths: {len(plan.updates)} (history written {plan.counts['written']}, deleted {plan.counts['deleted']})")
    if not args.apply:
        print("dry-run: nothing written (use --apply)")
        return 0
    if plan.empty:
        print("no changes")
        return 0
    client.update(plan.updates)
    print("applied")
    return 0
