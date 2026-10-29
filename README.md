# 🕵️ Diff Detective

**A small static-analysis tool that answers a bigger question: _what else might this code change affect?_**

Most Git diffs show *what changed*. Diff Detective also follows Python import relationships in reverse, to highlight modules that may be affected indirectly. No dependencies, API keys, or installation needed.

## Quick start

```bash
# Analyze Python modules from a project root (Python 3.11+)
python diff_detective.py --root /path/to/python/project --changed core.py

# Compare a Git reference against HEAD
python diff_detective.py --root /path/to/python/project --base HEAD~1

# Inspect staged changes
python diff_detective.py --root /path/to/python/project --staged

# Machine-readable output
python diff_detective.py --root /path/to/python/project --changed core.py --json
```

Pass `--root` to analyze a different Python project without modifying its source files.

## Example

Given `web.py → service.py → core.py` (each file imports the next), changing `core.py` produces:

```text
DIFF DETECTIVE | scanned 3 modules
Changed: core.py
Indirectly impacted: 2
  ! service.py  (via core.py -> service.py)
  ! web.py  (via core.py -> service.py -> web.py)
```

## How it works

1. Discover `.py` files under the specified project root.
2. Parse `import` and `from … import …` statements with the Python AST.
3. Resolve local module names, including simple relative imports.
4. Walk the reverse import graph with breadth-first search.
5. Print impacted modules and the shortest discovered dependency chain.

The JSON output includes `changed`, `impacted`, `impact_count`, `total_scanned`, and `warnings`.

## Run tests

```bash
python -m unittest discover -s tests -v
```

## Scope and limitations

This is **heuristic static analysis**, not a guarantee that files will break. It cannot reliably detect dynamic imports (`importlib`), runtime plugin loading, imports hidden behind generated code, or imports from external package roots configured through `PYTHONPATH`. It assumes project-root-relative Python modules. Changed paths are expected to be relative to `--root`.

## License

MIT © 2026 Ghassen258.
