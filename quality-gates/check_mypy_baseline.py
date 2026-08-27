#!/usr/bin/env python
"""G2 — mypy typecheck, baselined: FAIL only on NEW errors relative to a version-controlled
baseline (quality-gates/mypy-baseline.json). Same pattern as G1.

This repo carries 24 pre-existing mypy errors under this gate's own scoped config (measured
cold — `.mypy_cache` deleted before measuring, 2026-08-27; see `.claude/CLAUDE.md` ->
`## Code quality gates` for the full breakdown by file/code) — not fixed by this gate, recorded
in the baseline for a human to burn down.

**Host-provided / unstubbed-dependency imports are ignore_missing_imports, not baselined —
see `pyproject.toml` -> `[[tool.mypy.overrides]]` for the full, documented list and why each
entry is there** (ComfyUI host modules that never resolve in a bare interpreter: `comfy`,
`folder_paths`, `server`; optional manual-install RVC/TTS deps: `voxcpm`, `transformers`,
`pyworld`, `faiss`, `sounddevice`; always-installed-but-unstubbed core audio deps: `soundfile`,
`soxr`, `scipy`). Silencing those keeps this gate's signal on the repo's OWN code.

**Package-root workaround (this repo specifically):** the repo's own directory name
(`ComfyUI-misaka-prompt-manager`, and any worktree slug under `.claude/worktree/`) contains
hyphens, which is not a valid Python identifier. mypy's default implicit-namespace-package
inference refuses to name that directory as a package the moment `__init__.py` is checked
directly ("contains __init__.py but is not a valid Python package name") — `pyproject.toml`
sets `explicit_package_bases = true` + `mypy_path = "."` so mypy resolves module names from
its own config-file directory instead. This still leaves the repo's OWN `__init__.py` checked
as a bare `__main__` script (mypy CLI convention for a file with no enclosing package
argument), so its three relative imports (`from .nodes.image import ...`) resolve to
`__main__.nodes.*` and read as `import-not-found` — that is a structural artifact of checking
this ComfyUI plugin's entrypoint OUTSIDE the real `custom_nodes` package context ComfyUI's own
loader gives it at runtime (where the relative imports resolve fine), not a real bug in the
file. Those three findings are baselined like everything else rather than engineered around.

Identity key = "relative/file.py|CODE|message text", same line-drift-tolerant shape as G1.

**Crash guard + config-honoured guard:** see `lib/subprocess_gate.py` and
`lib/mypy_config_guard.py` docstrings — both required, and both verified against the
scratch-immunity + config-fail-open shapes documented in `.claude/CLAUDE.md`.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import baseline as baseline_lib
from lib import mypy_config_guard
from lib.git_diff import ensure_utf8_stdio
from lib.subprocess_gate import GateToolCrashed, print_crash_and_exit, run_with_exit_code_guard

ensure_utf8_stdio()

ROOT = Path(__file__).resolve().parent.parent
BASELINE_PATH = Path(__file__).resolve().parent / "mypy-baseline.json"
CONFIG_PATH = ROOT / "pyproject.toml"
CHECK_TARGETS = ["nodes", "voice", "__init__.py", "convert_workflows.py"]


def _run_mypy() -> list[dict]:
    problem = mypy_config_guard.verify_config_present(CONFIG_PATH)
    if problem:
        raise GateToolCrashed(
            "mypy",
            f"config not honoured before mypy even ran — {problem}",
            "",
        )

    proc = run_with_exit_code_guard(
        [sys.executable, "-m", "mypy", *CHECK_TARGETS, "--output=json", f"--config-file={CONFIG_PATH}"],
        cwd=ROOT,
        tool_name="mypy",
        success_codes={0, 1},  # 0 = clean, 1 = type errors found (verified empirically)
    )

    items: list[dict] = []
    non_json_lines: list[str] = []
    for stream in (proc.stdout, proc.stderr):
        for line in stream.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            try:
                items.append(json.loads(stripped))
            except json.JSONDecodeError:
                non_json_lines.append(stripped)  # not a finding — either a summary line or a
                # config-parse complaint; classified below.

    config_problems = mypy_config_guard.find_config_problem_lines(non_json_lines)
    if config_problems:
        raise GateToolCrashed(
            "mypy",
            "reported a config-parse problem — the configured strictness may not have been "
            "honoured for this run",
            "\n".join(config_problems),
        )

    errors = [item for item in items if item.get("severity") == "error"]
    if proc.returncode == 1 and not errors:
        raise GateToolCrashed(
            "mypy",
            "exited 1 (type errors found) but 0 error-severity findings were parsed from "
            "stdout/stderr — output shape may have changed",
            (proc.stdout + proc.stderr)[:2000],
        )
    return errors


def _identity(item: dict) -> str:
    rel = Path(item["file"]).as_posix()
    return f"{rel}|{item['code']}|{item['message']}"


def main() -> int:
    update_mode = "--update-baseline" in sys.argv[1:]
    try:
        items = _run_mypy()
    except GateToolCrashed as err:
        return print_crash_and_exit("G2", err)
    current = sorted({_identity(i) for i in items})

    if update_mode:
        baseline_lib.write(BASELINE_PATH, current)
        print(f"[G2] baseline updated — {len(current)} error(s) recorded at {BASELINE_PATH.name}.")
        return 0

    baseline = baseline_lib.load(BASELINE_PATH)
    new, resolved = baseline_lib.diff(current, baseline)

    if new:
        print(f"[G2] FAIL — {len(new)} NEW mypy error(s) not present in the baseline:", file=sys.stderr)
        for v in new:
            print(f"  - {v}", file=sys.stderr)
        print(
            f"\nBaseline: {BASELINE_PATH.name} ({len(baseline)} pre-existing error(s), unaffected).",
            file=sys.stderr,
        )
        return 1

    if resolved:
        print(
            f"[G2] FAIL — {len(resolved)} baseline error(s) no longer appear in the mypy "
            "output:",
            file=sys.stderr,
        )
        for v in resolved:
            print(f"  - {v}", file=sys.stderr)
        print(
            "\nThis is a FAIL, not a note: it can mean the finding was genuinely fixed, or "
            "that mypy silently stopped enforcing the check that used to catch it (broken "
            "config, weakened profile, etc). If you deliberately fixed the finding(s) above, "
            "re-run with --update-baseline to shrink the baseline. If you did NOT touch these "
            "files, investigate why mypy stopped reporting them before updating the baseline.",
            file=sys.stderr,
        )
        return 1

    print(f"[G2] PASS — {len(current)} total error(s), 0 new vs baseline ({len(baseline)} pre-existing).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
