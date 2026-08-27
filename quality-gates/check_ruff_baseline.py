#!/usr/bin/env python
"""G1 — ruff lint, baselined: FAIL only on NEW violations relative to a version-controlled
baseline (quality-gates/ruff-baseline.json).

Why baselined rather than a bare `ruff check .`: this repo was never linted before (single
existing test file, no CI) and carries 39 pre-existing violations under this gate's own scoped
config (`pyproject.toml` -> `[tool.ruff.lint] select = ["E4","E7","E9","F"]`, measured cold
2026-08-27 — see `.claude/CLAUDE.md` -> `## Code quality gates`) — a bare pass/fail would make
L0 permanently red on the untouched tree. This gate does NOT fix those 39 — they stay in the
baseline for a human to burn down; `--update-baseline` is for a deliberate, reviewed cleanup
(or knowingly accepting a new one), never a blanket bypass.

**Config isolation (important for this repo specifically):** this repo lives INSIDE a portable
ComfyUI installation that has its OWN `pyproject.toml` a few directories up
(`ComfyUI/pyproject.toml`, enabling `T20`/`W29x`/etc for ComfyUI's own codebase). ruff's config
discovery walks upward and would silently pick that file up (84 findings, mostly `print`-found
noise from this plugin's normal console-feedback style) if this repo did not carry its own
`pyproject.toml` with a `[tool.ruff]` table — ruff stops the upward search at the first
`pyproject.toml` it finds, so THIS repo's own file (committed at repo root) is what always
wins, in the main tree or any worktree. Measured both ways 2026-08-27: 84 findings against the
inherited ComfyUI config, 39 against this repo's own scoped one — the 39 is what is baselined.

Identity key = "relative/file.py|CODE|message text" — deliberately excludes the line number
so a violation that merely shifted a few lines from an unrelated edit above it doesn't
register as new.

**Crash guard:** `_run_ruff()` goes through `lib.subprocess_gate.run_with_exit_code_guard` with
`success_codes={0, 1}` — ruff's own exit codes for "clean" and "violations found" respectively
— so exit `2` (bad config, tool crash) raises `GateToolCrashed` instead of being silently
swallowed into "0 violations, PASS". Also guards the case where ruff's exit code says
"violations found" (`1`) but 0 items were parsed from stdout.

**Vanished-baseline-as-FAIL:** a baselined violation that stops appearing means either a
deliberate fix, or that this gate's check somehow stopped seeing it. This is a FAIL naming the
missing violation(s), with an explicit instruction to re-run with `--update-baseline` once the
improvement is confirmed intentional — never a silent PASS.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import baseline as baseline_lib
from lib.git_diff import ensure_utf8_stdio
from lib.subprocess_gate import GateToolCrashed, print_crash_and_exit, run_with_exit_code_guard

ensure_utf8_stdio()

ROOT = Path(__file__).resolve().parent.parent
BASELINE_PATH = Path(__file__).resolve().parent / "ruff-baseline.json"


def _run_ruff() -> list[dict]:
    proc = run_with_exit_code_guard(
        [sys.executable, "-m", "ruff", "check", ".", "--output-format=json"],
        cwd=ROOT,
        tool_name="ruff",
        success_codes={0, 1},  # 0 = clean, 1 = violations found (verified empirically)
    )
    try:
        items = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError as e:
        raise GateToolCrashed(
            "ruff",
            f"exited {proc.returncode} but stdout was not valid JSON ({e})",
            proc.stdout[:2000],
        ) from e
    if proc.returncode == 1 and not items:
        raise GateToolCrashed(
            "ruff",
            "exited 1 (violations found) but 0 findings were parsed from stdout — "
            "output shape may have changed",
            proc.stdout[:2000],
        )
    return items


def _identity(item: dict) -> str:
    rel = Path(item["filename"]).resolve().relative_to(ROOT).as_posix()
    return f"{rel}|{item['code']}|{item['message']}"


def main() -> int:
    update_mode = "--update-baseline" in sys.argv[1:]
    try:
        items = _run_ruff()
    except GateToolCrashed as err:
        return print_crash_and_exit("G1", err)
    current = sorted({_identity(i) for i in items})

    if update_mode:
        baseline_lib.write(BASELINE_PATH, current)
        print(f"[G1] baseline updated — {len(current)} violation(s) recorded at {BASELINE_PATH.name}.")
        return 0

    baseline = baseline_lib.load(BASELINE_PATH)
    new, resolved = baseline_lib.diff(current, baseline)

    if new:
        print(f"[G1] FAIL — {len(new)} NEW ruff violation(s) not present in the baseline:", file=sys.stderr)
        for v in new:
            print(f"  - {v}", file=sys.stderr)
        print(
            f"\nBaseline: {BASELINE_PATH.name} ({len(baseline)} pre-existing violation(s), unaffected).",
            file=sys.stderr,
        )
        return 1

    if resolved:
        print(
            f"[G1] FAIL — {len(resolved)} baseline violation(s) no longer appear in the ruff "
            "output:",
            file=sys.stderr,
        )
        for v in resolved:
            print(f"  - {v}", file=sys.stderr)
        print(
            "\nThis is a FAIL, not a note: if you deliberately fixed the violation(s) above, "
            "re-run with --update-baseline to shrink the baseline. If you did NOT touch these "
            "files, investigate why ruff stopped reporting them before updating the baseline.",
            file=sys.stderr,
        )
        return 1

    print(f"[G1] PASS — {len(current)} total violation(s), 0 new vs baseline ({len(baseline)} pre-existing).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
