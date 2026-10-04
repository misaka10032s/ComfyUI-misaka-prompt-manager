#!/usr/bin/env python
"""The test files a commit has to run: the staged test files, plus every test file that imports (statically, by
module path) a staged module. Used by `run.py commit`, so the commit step runs only these tests and never the whole
suite (the whole suite is `run.py l0`, the end-of-task run).

A test file is a file under `TEST_PATHS` (`tests/`, the folder this repo's pytest runs in) whose name matches
pytest's default `python_files`. A staged `conftest.py` counts as related to every test file under its folder.
Imports are read with `ast`, so `import a.b`, `from a import b` and `from a.b import c` all count, wherever in the
file they stand. A staged module is named by its dotted path from the repo root (`voice/_safe_load.py` is
`voice._safe_load`, `voice/__init__.py` is `voice` and also covers every `voice.*` import) and, when its folder has
no `__init__.py`, by its bare file name (which pytest puts on the path for the tests beside it).

Usage (from the repo root):  py -3.11 quality-gates/related_tests.py   (prints the files, one per line)
"""
from __future__ import annotations

import ast
import fnmatch
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.git_diff import ensure_utf8_stdio, get_staged_files

ROOT = Path(__file__).resolve().parent.parent  # repo root
TEST_PATHS = ["tests"]
PYTHON_FILES = ["test_*.py", "*_test.py"]


def all_test_files(root: Path) -> list[str]:
    """Every test file pytest collects here, as paths relative to `root`."""
    found: set[str] = set()
    for testpath in TEST_PATHS:
        base = root / testpath
        for path in base.rglob("*.py"):
            if any(fnmatch.fnmatch(path.name, pattern) for pattern in PYTHON_FILES):
                found.add(path.relative_to(root).as_posix())
    return sorted(found)


def module_names(root: Path, rel: str) -> tuple[set[str], bool]:
    """(names the module can be imported by, whether it is a package `__init__`)."""
    parts = rel[: -len(".py")].split("/")
    is_package = parts[-1] == "__init__"
    dotted_parts = parts[:-1] if is_package else parts
    names: set[str] = set()
    if dotted_parts and all(part.isidentifier() for part in dotted_parts):
        names.add(".".join(dotted_parts))
    if not is_package and not (root / Path(*parts[:-1]) / "__init__.py").exists():
        names.add(parts[-1])  # a bare module on a test folder's own path
    return names, is_package


def imported_names(path: Path) -> set[str]:
    """Every module name the file imports, plus `package.name` for each `from package import name`."""
    names: set[str] = set()
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def related_test_files(root: Path = ROOT) -> list[str]:
    """Staged test files plus the test files that import a staged module, relative to `root`, sorted."""
    staged = get_staged_files(root, ["py"])
    tests = all_test_files(root)
    related = {rel for rel in staged if rel in tests}
    for rel in staged:
        if rel.rsplit("/", 1)[-1] == "conftest.py":
            folder = rel.rsplit("/", 1)[0] + "/" if "/" in rel else ""
            related |= {test for test in tests if test.startswith(folder)}
    exact: set[str] = set()
    packages: set[str] = set()
    for rel in staged:
        names, is_package = module_names(root, rel)
        exact |= names
        if is_package:
            packages |= names
    if exact:
        for rel in tests:
            if rel in related:
                continue
            for name in imported_names(root / rel):
                if name in exact or any(name.startswith(package + ".") for package in packages):
                    related.add(rel)
                    break
    return sorted(related)


def main() -> int:
    ensure_utf8_stdio()
    for rel in related_test_files():
        print(rel)
    return 0


if __name__ == "__main__":
    sys.exit(main())
