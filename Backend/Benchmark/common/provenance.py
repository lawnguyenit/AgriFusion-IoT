from __future__ import annotations

from pathlib import Path


def resolve_code_commit(repo_root: Path) -> str:
    head_path = repo_root / ".git" / "HEAD"
    if not head_path.exists():
        return "UNKNOWN"
    try:
        head_value = head_path.read_text(encoding="utf-8").strip()
        if head_value.startswith("ref: "):
            ref_path = repo_root / ".git" / head_value.split(" ", 1)[1].strip().replace("/", "\\")
            if ref_path.exists():
                return ref_path.read_text(encoding="utf-8").strip()
        return head_value
    except Exception:
        return "UNKNOWN"
