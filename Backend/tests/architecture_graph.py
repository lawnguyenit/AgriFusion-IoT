"""Import graph between top-level packages (used by the architecture test).

Nodes
  settings | io | ingest | canonical | cloud   src/agrifusion/<name>/**
  cli                                          src/agrifusion/cli.py, __main__.py
  agrifusion                                   other files directly in src/agrifusion/
  research                                     files directly in research/agrifusion_research/ (cli)
  core.<sub> | external.<sub> | experiments.<sub>
                                               research/agrifusion_research/<group>/<sub>/**
                                               (core.gates = pretrain_audit + validity_lifecycle;
                                               files directly in <group>/ map to <group>)
  Backend                                      Backend/main.py (deprecated shim), Backend/__init__.py

Only edges between two different nodes are recorded. Backend/tests/ is not part of the graph.
Imports are found with ast (including imports inside functions and try/except blocks) and
relative imports are resolved against the file's own package.
"""
from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
RESEARCH_ROOT = REPO_ROOT / "research"
RESEARCH_PACKAGE = "agrifusion_research"
RESEARCH_DIR = RESEARCH_ROOT / RESEARCH_PACKAGE
RESEARCH_GROUPS = ("core", "external", "experiments")
BACKEND_DIR = REPO_ROOT / "Backend"

AGRIFUSION_SUBPACKAGES = ("settings", "io", "ingest", "canonical", "cloud")
AGRIFUSION_NODES = frozenset({*AGRIFUSION_SUBPACKAGES, "cli", "agrifusion"})


def node_for_parts(parts: list[str]) -> str | None:
    """Map an absolute dotted module path (as parts) to a graph node, or None if not in the graph."""
    if not parts:
        return None
    if parts[0] == "agrifusion":
        if len(parts) == 1:
            return "agrifusion"
        if parts[1] in AGRIFUSION_SUBPACKAGES:
            return parts[1]
        if parts[1] in {"cli", "__main__"}:
            return "cli"
        return "agrifusion"
    if parts[0] == "Backend":
        if len(parts) == 1 or parts[1] == "main":
            return "Backend"
        return None
    if parts[0] == RESEARCH_PACKAGE:
        if len(parts) == 1 or parts[1] not in RESEARCH_GROUPS:
            return "research"
        group = parts[1]
        if len(parts) >= 3 and (RESEARCH_DIR / group / parts[2]).is_dir():
            return f"{group}.{parts[2]}"
        return group
    return None  # tests, third-party, stdlib


def _module_parts(path: Path) -> list[str] | None:
    """Absolute dotted parts of a source file, or None when the file is outside the graph."""
    resolved = path.resolve()
    for root in (SRC_ROOT, RESEARCH_ROOT, REPO_ROOT):
        try:
            parts = list(resolved.relative_to(root).with_suffix("").parts)
        except ValueError:
            continue
        if root == REPO_ROOT and parts[0] != "Backend":
            continue
        return parts
    return None


def _file_node(path: Path) -> str | None:
    parts = _module_parts(path)
    if parts is None or parts[:2] == ["Backend", "tests"]:
        return None
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return node_for_parts(parts)


def _package_parts(path: Path) -> list[str]:
    parts = _module_parts(path)
    assert parts is not None
    return parts[:-1]  # drops the module (or __init__) name -> the containing package


def _imported_modules(tree: ast.AST, pkg_parts: list[str]) -> list[tuple[list[str], int]]:
    """Return (absolute module parts, lineno) for every import in the tree."""
    found: list[tuple[list[str], int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.append((alias.name.split("."), node.lineno))
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                keep = len(pkg_parts) - (node.level - 1)
                if keep < 0:
                    continue
                module_parts = pkg_parts[:keep] + (node.module.split(".") if node.module else [])
            else:
                module_parts = (node.module or "").split(".")
            found.append((module_parts, node.lineno))
            for alias in node.names:  # `from pkg import subpkg`
                found.append((module_parts + [alias.name], node.lineno))
    return found


def build_edges(repo_root: Path = REPO_ROOT) -> dict[tuple[str, str], list[str]]:
    """Return {(src_node, dst_node): ["relative/file.py:line", ...]} for cross-node imports."""
    edges: dict[tuple[str, str], set[str]] = {}
    files = (
        sorted((repo_root / "src" / "agrifusion").rglob("*.py"))
        + sorted((repo_root / "research" / RESEARCH_PACKAGE).rglob("*.py"))
        + sorted((repo_root / "Backend").rglob("*.py"))
    )
    for path in files:
        if "__pycache__" in path.parts:
            continue
        src = _file_node(path)
        if src is None:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        pkg_parts = _package_parts(path)
        rel = path.relative_to(repo_root).as_posix()
        for module_parts, lineno in _imported_modules(tree, pkg_parts):
            dst = node_for_parts(module_parts) if module_parts else None
            if dst is None or dst == src:
                continue
            edges.setdefault((src, dst), set()).add(f"{rel}:{lineno}")
    return {edge: sorted(where) for edge, where in sorted(edges.items())}


def mutual_pairs(edges: set[tuple[str, str]]) -> list[tuple[str, str]]:
    return sorted({tuple(sorted((a, b))) for (a, b) in edges if (b, a) in edges})  # type: ignore[misc]
