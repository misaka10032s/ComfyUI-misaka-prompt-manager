#!/usr/bin/env python
"""Aggregate quality-gate runner — L0 ONLY (deliberate scope decision, not a partial rollout).

Usage (from the repo root):
    py -3.11 quality-gates/run.py <g1|g2|g3|commit|l0> [--update-baseline]

  commit = the fast steps the pre-commit hook runs, within about 10 seconds: ruff on the STAGED .py files only (no
       mypy), the determinism scan, the assertion check on the staged test files, and pytest on the RELATED test files
       only (`related_tests.py`: the staged test files, the test files that import a staged module, and every test
       file under a staged `conftest.py`'s folder; none -> it says so and passes). Whole-suite pytest and mypy stay in
       l0, the end-of-task run.
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

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.git_diff import ensure_utf8_stdio
from related_tests import related_test_files

ensure_utf8_stdio()

ROOT = Path(__file__).resolve().parent.parent  # repo root
GATES_DIR = Path(__file__).resolve().parent  # quality-gates/
TESTS_DIR = ROOT / "tests"


def _run(cmd: list[str], cwd: Path) -> int:
    print(f"$ {' '.join(cmd)}  (cwd={cwd})")
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


def commit() -> int:
    """The pre-commit level: staged-file ruff, the determinism scan, the assertion check on staged test files, and the
    related tests (see the module docstring). l0 stays the end-of-task run. pytest runs with the same cwd and
    --rootdir/--confcutdir as g3 (see the module docstring), on the related test files by absolute path."""
    rc = _run([sys.executable, str(GATES_DIR / "check_ruff_baseline.py"), "--staged"], ROOT)
    if rc != 0:
        return rc
    rc = _run([sys.executable, str(GATES_DIR / "check_test_determinism.py")], ROOT)
    if rc != 0:
        return rc
    rc = _run([sys.executable, str(GATES_DIR / "check_test_assertions.py"), "--staged"], ROOT)
    if rc != 0:
        return rc
    related = related_test_files(ROOT)
    if not related:
        print("[commit] no staged test file and no test file importing a staged module - no related test to run.")
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
