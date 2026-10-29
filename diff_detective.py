#!/usr/bin/env python3
"""Diff Detective: lightweight, dependency-aware Python change impact analysis."""

from __future__ import annotations

import argparse
import ast
from collections import deque
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", ".mypy_cache", ".pytest_cache", "node_modules", "build", "dist"}


def discover(root: Path) -> dict[str, str]:
    """Map importable dotted module names to relative Python file paths."""
    modules = {}
    for file in sorted(root.rglob("*.py")):
        rel = file.relative_to(root)
        if any(part in SKIP_DIRS or part.startswith(".") for part in rel.parts):
            continue
        parts = list(rel.with_suffix("").parts)
        if parts[-1] == "__init__":
            parts.pop()
        if parts:
            modules[".".join(parts)] = rel.as_posix()
    return modules


def dependencies(root: Path) -> tuple[dict[str, set[str]], list[str]]:
    modules = discover(root)
    edges = {path: set() for path in modules.values()}
    warnings = []
    for module, path in modules.items():
        try:
            tree = ast.parse((root / path).read_text(encoding="utf-8"), filename=path)
        except (SyntaxError, UnicodeError) as exc:
            warnings.append(f"Could not parse {path}: {exc}")
            continue
        package = module.split(".") if path.endswith("/__init__.py") or path == "__init__.py" else module.split(".")[:-1]
        for node in ast.walk(tree):
            candidates: list[str] = []
            if isinstance(node, ast.Import):
                candidates.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                # level 1 = current package, level 2 = parent package, etc.
                if node.level:
                    keep = len(package) - (node.level - 1)
                    if keep < 0:
                        continue
                    base = package[:keep]
                    prefix = ".".join(base + ([node.module] if node.module else []))
                else:
                    prefix = node.module or ""
                candidates.extend(f"{prefix}.{alias.name}" if prefix else alias.name for alias in node.names if alias.name != "*")
                if prefix:
                    candidates.append(prefix)
            for candidate in candidates:
                # Resolve exact module first, then its enclosing package.
                parts = candidate.split(".")
                for length in range(len(parts), 0, -1):
                    resolved = modules.get(".".join(parts[:length]))
                    if resolved:
                        if resolved != path:
                            edges[path].add(resolved)
                        break
    return edges, warnings


def analyze(edges: dict[str, set[str]], changed: list[str]) -> dict[str, Any]:
    reverse: dict[str, set[str]] = {path: set() for path in edges}
    for source, imports in edges.items():
        for dependency in imports:
            reverse.setdefault(dependency, set()).add(source)
    changed_set = set(changed)
    queue = deque((path, [path]) for path in sorted(changed_set))
    visited = set(changed_set)
    affected: dict[str, list[str]] = {}
    while queue:
        current, chain = queue.popleft()
        for consumer in sorted(reverse.get(current, [])):
            if consumer not in visited:
                visited.add(consumer)
                new_chain = chain + [consumer]
                affected[consumer] = new_chain
                queue.append((consumer, new_chain))
    return {
        "changed": sorted(changed_set),
        "impacted": [{"file": f, "via": affected[f]} for f in sorted(affected)],
        "impact_count": len(affected),
        "total_scanned": len(edges),
    }


def git_changed(root: Path, base: str, staged: bool = False) -> list[str]:
    args = ["git", "-C", str(root), "diff", "--name-only"]
    if staged:
        args.append("--cached")
    else:
        args += [base, "HEAD"]
    completed = subprocess.run(args, text=True, capture_output=True, check=False)
    if completed.returncode:
        raise ValueError(completed.stderr.strip() or "git diff failed")
    return [p for p in completed.stdout.splitlines() if p.endswith(".py")]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Trace the indirect impact of changed Python modules.")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Python project root (default: current directory)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--changed", nargs="+", metavar="FILE", help="Changed paths relative to the project root")
    group.add_argument("--base", metavar="REF", help="Compare Git REF to HEAD, e.g. HEAD~1")
    group.add_argument("--staged", action="store_true", help="Analyze staged Python changes")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    if not root.is_dir():
        parser.error(f"Not a directory: {root}")
    try:
        changed = args.changed if args.changed is not None else git_changed(root, args.base or "HEAD", args.staged)
    except ValueError as exc:
        parser.error(str(exc))
    cleaned = sorted({Path(item.replace("\\", "/")).as_posix().removeprefix("./") for item in changed if item.endswith(".py")})
    edges, warnings = dependencies(root)
    result = analyze(edges, cleaned)
    result["warnings"] = warnings
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"DIFF DETECTIVE | scanned {result['total_scanned']} modules")
        print(f"Changed: {', '.join(result['changed']) or '(none)'}")
        print(f"Indirectly impacted: {result['impact_count']}")
        for item in result["impacted"]:
            print(f"  ! {item['file']}  (via {' -> '.join(item['via'])})")
        for warning in warnings:
            print(f"  warning: {warning}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
