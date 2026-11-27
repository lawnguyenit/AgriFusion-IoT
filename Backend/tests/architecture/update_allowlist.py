"""Rewrite allowed_import_edges.txt from the CURRENT import graph, keeping existing comments.

    python Backend/tests/architecture/update_allowlist.py

Use only when a new/removed dependency between top-level packages is intended; review the git diff.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from Backend.tests.architecture_graph import build_edges  # noqa: E402

ALLOWLIST = Path(__file__).resolve().parent / "allowed_import_edges.txt"

HEADER = """\
# Allowed import edges between top-level packages (src/agrifusion/* and research/agrifusion_research/*).
# Format: `<importer> -> <imported>   # optional comment`. Nodes: see Backend/tests/architecture_graph.py.
# Backend/tests/test_architecture_import_graph.py fails when the code has an edge NOT listed here.
# Removing an edge from the code is always fine (stale lines only produce a warning); delete the line then.
# Adding an edge needs a deliberate decision: regenerate with
#   python Backend/tests/architecture/update_allowlist.py
# and justify the new line in the commit message.
"""


def parse_comments(text: str) -> dict[str, str]:
    comments: dict[str, str] = {}
    for line in text.splitlines():
        if line.startswith("#") or "->" not in line:
            continue
        body, _, comment = line.partition("#")
        comments[body.strip()] = comment.strip()
    return comments


def main() -> None:
    old = parse_comments(ALLOWLIST.read_text(encoding="utf-8")) if ALLOWLIST.exists() else {}
    lines = [HEADER]
    for (src, dst) in build_edges():
        key = f"{src} -> {dst}"
        comment = old.get(key, "")
        lines.append(f"{key}   # {comment}" if comment else key)
    ALLOWLIST.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {len(lines) - 1} edges to {ALLOWLIST}")


if __name__ == "__main__":
    main()
