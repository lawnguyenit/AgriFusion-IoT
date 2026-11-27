"""Import graph between top-level packages of Backend (used by the architecture test).

Nodes
  Config                 Backend/Config/**
  Core.<sub>             Backend/Navigation/Core/<sub>/**   (Core = files directly in Core/)
  Benchmark.<sub>        Backend/Benchmark/<sub>/**         (Benchmark = files directly in Benchmark/)
  Backend                Backend/main.py, Backend/__init__.py

Only edges between two different nodes are recorded. tests/ is not part of the graph.
Imports are found with ast (including imports inside functions and try/except fallbacks),
relative imports are resolved, and the bare spellings used by the code base
(`from Config.runtime import ...`, `from Navigation.Core import ...`) are mapped like the
`Backend.`-prefixed ones.
"""
from __future__ import annotations

import ast
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]


def node_for_parts(parts: list[str]) -> str | None:
    """Map a dotted module path *relative to Backend* (as parts) to a graph node."""
    if not parts:
        return "Backend"
    head = parts[0]
    if head == "Config":
        return "Config"
    if head == "Navigation" and len(parts) >= 2 and parts[1] == "Core":
        if len(parts) >= 3 and (BACKEND_DIR / "Navigation" / "Core" / parts[2]).is_dir():
            return f"Core.{parts[2]}"
        return "Core"
    if head == "Navigation":
        return "Core" if len(parts) == 1 else None
    if head == "Benchmark":
        if len(parts) >= 2 and (BACKEND_DIR / "Benchmark" / parts[1]).is_dir():
            return f"Benchmark.{parts[1]}"
        return "Benchmark"
    if head == "main":
        return "Backend"
    return None


def _file_node(path: Path) -> str | None:
    rel = path.resolve().relative_to(BACKEND_DIR)
    parts = list(rel.parts)
    if parts[0] in {"tests", "Output_data"}:
        return None
    if parts[0] == "Config":
        return "Config"
    if parts[:2] == ["Navigation", "Core"]:
        # a file directly in Core/ has parts == [Navigation, Core, file.py]
        return f"Core.{parts[2]}" if len(parts) >= 4 else "Core"
    if parts[0] == "Benchmark":
        return f"Benchmark.{parts[1]}" if len(parts) >= 3 else "Benchmark"
    if len(parts) == 1:
        return "Backend"
    return None  # e.g. Navigation/*.md-only areas


def _package_parts(path: Path) -> list[str]:
    rel = path.resolve().relative_to(BACKEND_DIR)
    parts = list(rel.with_suffix("").parts)
    return parts[:-1] if parts[-1] != "__init__" else parts[:-1]


def _imported_modules(tree: ast.AST, pkg_parts: list[str]) -> list[tuple[list[str], int]]:
    """Return (module parts relative to Backend, lineno) for every import in the tree."""
    found: list[tuple[list[str], int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.append((_strip_backend(alias.name.split(".")), node.lineno))
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                keep = len(pkg_parts) - (node.level - 1)
                if keep < 0:
                    continue
                base = pkg_parts[:keep]
                module_parts = base + (node.module.split(".") if node.module else [])
            else:
                module_parts = _strip_backend((node.module or "").split("."))
            found.append((module_parts, node.lineno))
            for alias in node.names:  # `from pkg import subpkg`
                found.append((module_parts + [alias.name], node.lineno))
    return found


def _strip_backend(parts: list[str]) -> list[str]:
    if parts and parts[0] == "Backend":
        return parts[1:]
    return parts


def build_edges(backend_dir: Path = BACKEND_DIR) -> dict[tuple[str, str], list[str]]:
    """Return {(src_node, dst_node): ["relative/file.py:line", ...]} for cross-node imports."""
    edges: dict[tuple[str, str], set[str]] = {}
    for path in sorted(backend_dir.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        src = _file_node(path)
        if src is None:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        pkg_parts = _package_parts(path)
        rel = path.relative_to(backend_dir).as_posix()
        for module_parts, lineno in _imported_modules(tree, pkg_parts):
            dst = node_for_parts(module_parts) if module_parts else None
            if dst is None or dst == src:
                continue
            edges.setdefault((src, dst), set()).add(f"{rel}:{lineno}")
    return {edge: sorted(where) for edge, where in sorted(edges.items())}


def mutual_pairs(edges: set[tuple[str, str]]) -> list[tuple[str, str]]:
    return sorted({tuple(sorted((a, b))) for (a, b) in edges if (b, a) in edges})  # type: ignore[misc]
