#!/usr/bin/env python
"""Aggregate quality-gate runner — L0 ONLY (deliberate scope decision, not a partial rollout).

Usage (from the repo root):
    py -3.11 quality-gates/run.py <g1|g2|g3|commit|l0> [--update-baseline]

  commit = what the pre-commit hook runs, within about 10 seconds, only the steps the change class of the staged files
       needs: it classes every staged file by path (code, test, setup, tooling, docs, style, wording), prints the class
       counts, then runs ruff on the STAGED .py files (no mypy) when a .py of class code, test, setup or tooling is
       staged, the determinism scan of the staged test, setup and tooling files only (`--files`), the assertion check
       when a test file is staged, and pytest on the RELATED test files only (`related_tests.py`: the staged test
       files, the test files that import or name a staged file; none -> it says so and passes) unless a setup file is
       staged (then the tests move to the end-of-task run). Whole-suite pytest and mypy stay in l0, the end-of-task run.
  l0 = G1 (ruff lint, baselined) + G2 (mypy typecheck, baselined) + G3 (pytest green +
       assertion-presence on new/changed tests) — seconds-level.

**Why L0 only, no L1/L2:** this repo's tests are the files under `tests/`.
Diff coverage (L1) and mutation testing (L2) are theatre, not signal, at that test
size — there is nothing for a coverage/mutation gate to meaningfully measure against. This
scope decision was made before this recipe was installed (see `.claude/CLAUDE.md` ->
`## Code quality gates`) and is not to be silently expanded.

**G3's pytest invocation is deliberately unusual — read before changing it.** This repo is a
ComfyUI custom node living INSIDE a portable ComfyUI installation
(`ComfyUI/custom_nodes/ComfyUI-misaka-prompt-manager/`), and that installation carries its own
`ComfyUI/pytest.ini`. Because this repo's own root `__init__.py` sits directly above `tests/`,
pytest's `Package` collector (this is unconditional pytest behaviour, independent of
`--import-mode`: any `__init__.py`-bearing directory on the walked path becomes a `Package`
node, and `Package.setup()` unconditionally imports that directory's `__init__.py`) tries to
import this plugin's REAL entrypoint — which does `import comfy.sd` and pulls in the actual
ComfyUI host package, breaking on whatever the live install's own optional modules are missing
(measured 2026-08-27: `ModuleNotFoundError: No module named 'comfy_aimdo'`, unrelated to this
repo entirely). Invoking pytest with `cwd=tests/` AND explicit `--rootdir=. --confcutdir=.`
stops the ancestor walk exactly at `tests/` (which has no `__init__.py` of its own), so no
`Package` node for the repo root is ever constructed and `__init__.py` is never imported by
pytest. Verified empirically (`.claude/CLAUDE.md` -> `## Code quality gates` has the full
before/after) — do not "simplify" this back to `pytest tests/` from the repo root; that
reintroduces the failure.

Every gate here is a thin wrapper around a real external command — this script's only job is
consistent naming/sequencing.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.git_diff import _git, ensure_utf8_stdio, repo_prefix
from related_tests import related_test_files

ensure_utf8_stdio()

ROOT = Path(__file__).resolve().parent.parent  # repo root
GATES_DIR = Path(__file__).resolve().parent  # quality-gates/
TESTS_DIR = ROOT / "tests"

# --- commit level: the package constants (a copy of this recipe edits only this block) --------------------------------
# Class patterns match a path relative to the repo root with forward slashes ('../' for a hook above the package root).
# The class of a file is the first rule that matches, in this order: setup, tooling, test, docs, style, wording, code.
SETUP_PATTERNS = [
    re.compile(r"(?:^|/)conftest\.py$"),
    re.compile(r"^pytest\.ini$"),
    re.compile(r"^pyproject\.toml$"),
    re.compile(r"(?:^|/)requirements[^/]*\.txt$"),
]
TOOLING_PATTERNS = [
    re.compile(r"^quality-gates/"),
    re.compile(r"(?:^|/)determinism-canaries/"),
    re.compile(r"^(?:\.\./)*\.githooks/pre-commit$"),
]
TEST_FOLDERS = ("tests/",)  # every file under them is a test or a test helper
WORDING_PATTERNS: list[re.Pattern[str]] = []  # no locale files in this package
# Related tests at commit (rule R of the commit-level design): True when a recorded run of this package's test step fits
# the 10-second commit. TEST_CAP: the most related test files allowed (None: no cap).
TESTS_AT_COMMIT = True
TEST_CAP: int | None = None
# --- end of the commit-level constants ---------------------------------------------------------------------------------

CLASS_ORDER = ("code", "test", "setup", "tooling", "docs", "style", "wording")


def _run(cmd: list[str], cwd: Path) -> int:
    print(f"$ {' '.join(cmd)}  (cwd={cwd})", flush=True)
    return subprocess.run(cmd, cwd=cwd).returncode


def g1(update_baseline: bool = False) -> int:
    cmd = [sys.executable, str(GATES_DIR / "check_ruff_baseline.py")]
    if update_baseline:
        cmd.append("--update-baseline")
    return _run(cmd, ROOT)


def g2(update_baseline: bool = False) -> int:
    cmd = [sys.executable, str(GATES_DIR / "check_mypy_baseline.py")]
    if update_baseline:
        cmd.append("--update-baseline")
    return _run(cmd, ROOT)


def g3() -> int:
    # See module docstring: cwd=tests/ + explicit --rootdir/--confcutdir is load-bearing, not
    # a style choice — it is what stops pytest importing this plugin's real __init__.py.
    rc = _run(
        [sys.executable, "-m", "pytest", "-q", "--rootdir=.", "--confcutdir=."],
        TESTS_DIR,
    )
    if rc != 0:
        return rc
    # Assertion-presence scans the *diff*, so it needs the real repo root as cwd (git_diff's
    # get_changed_files/get_changed_line_ranges resolve paths relative to cwd).
    rc = _run([sys.executable, str(GATES_DIR / "check_test_assertions.py")], ROOT)
    if rc != 0:
        return rc
    # Determinism (G3c) scans the WHOLE test scope on every run, never the diff, so cwd is the repo root.
    return _run([sys.executable, str(GATES_DIR / "check_test_determinism.py")], ROOT)


def _class_of(rel: str) -> str:
    """The change class of a path relative to the repo root, by the first matching rule (the git status is not looked at here)."""
    if any(pattern.search(rel) for pattern in SETUP_PATTERNS):
        return "setup"
    if any(pattern.search(rel) for pattern in TOOLING_PATTERNS):
        return "tooling"
    if rel.startswith(TEST_FOLDERS):
        return "test"
    if (
        re.search(r"\.(?:md|mdx)$", rel, re.I)
        or (re.search(r"\.txt$", rel, re.I) and not re.search(r"(?:^|/)requirements[^/]*\.txt$", rel))
        or rel.startswith("docs/")
    ):
        return "docs"
    if re.search(r"\.(?:css|scss|sass|less)$", rel, re.I):
        return "style"
    if any(pattern.search(rel) for pattern in WORDING_PATTERNS):
        return "wording"
    return "code"


def _staged_entries() -> list[tuple[str, str, str]]:
    """The staged entries that belong to the package, each (status, path relative to it, class). Files outside it are
    dropped, except the repo's pre-commit hook. A staged delete (D) or rename (R) of a code or test file is class setup."""
    fields = _git(["diff", "--cached", "--name-status", "-M", "-z"], ROOT).split("\0")
    prefix = repo_prefix(ROOT).replace("\\", "/")
    depth = len([part for part in prefix.split("/") if part])
    entries: list[tuple[str, str, str]] = []
    i = 0
    while i < len(fields) and fields[i] != "":
        status = fields[i][0]
        count = 2 if status in ("R", "C") else 1
        top = fields[i + count].replace("\\", "/")
        i += 1 + count
        if prefix == "" or top.startswith(prefix):
            rel = top[len(prefix):]
        elif top == ".githooks/pre-commit":
            rel = "../" * depth + top
        else:
            continue
        cls = _class_of(rel)
        if status in ("D", "R") and cls in ("code", "test"):
            cls = "setup"
        entries.append((status, rel, cls))
    return entries


def commit() -> int:
    """The pre-commit level: classes the staged files by path, prints the class counts, and runs only the steps the classes
    need (see the module docstring); a step that fails stops the run. l0 stays the end-of-task run. pytest runs with the
    same cwd and --rootdir/--confcutdir as g3 (see the module docstring), on the related test files by absolute path."""
    entries = _staged_entries()
    counts = {name: sum(1 for _, _, cls in entries if cls == name) for name in CLASS_ORDER}
    print("[commit] classes: " + " ".join(f"{name}={counts[name]}" for name in CLASS_ORDER), flush=True)
    # A deleted path has nothing to lint or scan (a rename's entry holds the new path).
    alive = [(rel, cls) for status, rel, cls in entries if status != "D"]
    if any(rel.endswith(".py") and cls in ("test", "code", "setup", "tooling") for rel, cls in alive):
        rc = _run([sys.executable, str(GATES_DIR / "check_ruff_baseline.py"), "--staged"], ROOT)
        if rc != 0:
            return rc
    scanned = [rel for rel, cls in alive if cls in ("test", "setup", "tooling")]
    if scanned:
        rc = _run([sys.executable, str(GATES_DIR / "check_test_determinism.py"), "--files", *scanned], ROOT)
        if rc != 0:
            return rc
    if any(cls == "test" and re.search(r"(?:^|/)(?:test_[^/]*|[^/]*_test)\.py$", rel) for rel, cls in alive):
        rc = _run([sys.executable, str(GATES_DIR / "check_test_assertions.py"), "--staged"], ROOT)
        if rc != 0:
            return rc
    if not TESTS_AT_COMMIT:
        return 0
    setup_entries = [(status, rel) for status, rel, cls in entries if cls == "setup"]
    if setup_entries:
        status, rel = setup_entries[0]
        if status in ("D", "R"):
            print(f"[commit] {rel} was deleted or renamed: the tests move to the end-of-task run", flush=True)
        else:
            print(f"[commit] {rel} is test setup: the tests move to the end-of-task run", flush=True)
        return 0
    related = related_test_files(ROOT)
    if not related:
        print("[commit] no staged test file and no test file related to a staged file - no related test to run.", flush=True)
        return 0
    if TEST_CAP is not None and len(related) > TEST_CAP:
        print(f"[commit] {len(related)} related test files > {TEST_CAP}: the tests move to the end-of-task run", flush=True)
        return 0
    files = [str(ROOT / rel) for rel in related]
    return _run([sys.executable, "-m", "pytest", "-q", "--rootdir=.", "--confcutdir=.", *files], TESTS_DIR)


def l0(update_baseline: bool = False) -> int:
    gates = (
        lambda: g1(update_baseline),
        lambda: g2(update_baseline),
        g3,
    )
    for gate in gates:
        rc = gate()
        if rc != 0:
            return rc
    return 0


GATES = {"g1": g1, "g2": g2, "g3": g3, "commit": commit, "l0": l0}


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in GATES:
        print(f"usage: run.py <{'|'.join(GATES)}> [--update-baseline]", file=sys.stderr)
        return 2
    name = sys.argv[1]
    update_baseline = "--update-baseline" in sys.argv[2:]
    if name in ("g1", "g2", "l0"):
        return GATES[name](update_baseline)
    return GATES[name]()


if __name__ == "__main__":
    sys.exit(main())
