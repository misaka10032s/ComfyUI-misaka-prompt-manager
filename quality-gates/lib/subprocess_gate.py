"""Shared "did the wrapped tool actually run, or did it crash" guard for gates that shell out
to a lint/type-check tool and parse its stdout (G1 ruff, G2 mypy).

Ported verbatim from learningMachine's Python-family quality-gates recipe
(api/quality-gates/lib/subprocess_gate.py, 2026-08-27 fail-open audit) — that audit found none
of ruff/mypy/import-linter distinguished a genuine tool crash (bad config, internal error, tool
not runnable) from "the tool ran cleanly and found zero violations": both produce empty/
unparsable stdout, and a naive `json.loads(stdout or "[]")` silently reports "0 findings, PASS"
for a crash. This repo only carries G1/G2 (no G4 import-linter), so only the ruff/mypy exit-code
semantics below apply.

Exit-code semantics (verified empirically on the source repo, 2026-08-27 — re-verified here
2026-08-27 against THIS repo's own ruff 0.15.12 / mypy 1.20.2):

- **ruff check --output-format=json**: exit `0` = clean (no violations), exit `1` = violations
  found, exit `2` = usage/internal error (e.g. `--config` pointing at a nonexistent file).
  JSON is written to stdout for `0`/`1`; on `2`, stdout is empty and the error message is on
  stderr.
- **mypy --output=json**: exit `0` = clean, exit `1` = type errors found, exit `2` = fatal
  error (e.g. `--config-file` pointing at a nonexistent file). Same stdout/stderr split as
  ruff.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


class GateToolCrashed(Exception):
    """The wrapped tool did not run to completion. Callers must print `.stderr_text` (or
    whatever text explains the cause) and exit non-zero — NEVER swallow this into a
    "0 findings" PASS."""

    def __init__(self, tool_name: str, reason: str, evidence_text: str = "") -> None:
        self.tool_name = tool_name
        self.reason = reason
        self.evidence_text = evidence_text
        super().__init__(f"{tool_name} did not complete: {reason}")


def run_with_exit_code_guard(
    cmd: list[str],
    cwd: Path,
    *,
    tool_name: str,
    success_codes: set[int],
) -> subprocess.CompletedProcess:
    """Run `cmd`, raising `GateToolCrashed` if its exit code is not one of `success_codes`.

    `success_codes` is an explicit ALLOW-list (not a deny-list of known-bad codes) — an exit
    code nobody has seen before is treated as a crash, never silently accepted as "must be
    fine". Use for tools whose exit code reliably distinguishes "ran, N findings" from
    "crashed" — that is ruff and mypy.
    """
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if proc.returncode not in success_codes:
        raise GateToolCrashed(
            tool_name,
            f"exit code {proc.returncode} not in the expected {sorted(success_codes)}",
            proc.stderr,
        )
    return proc


def print_crash_and_exit(gate_tag: str, err: GateToolCrashed) -> int:
    """Uniform crash-report shape for every gate's `main()`. Always returns 1 — callers do
    `return print_crash_and_exit("G1", err)` from an `except GateToolCrashed as err:` block."""
    print(f"[{gate_tag}] FAIL — {err.tool_name} {err.reason}.", file=sys.stderr)
    if err.evidence_text.strip():
        print(f"\n{err.tool_name} output:\n{err.evidence_text.strip()}", file=sys.stderr)
    print(
        f"\n[{gate_tag}] the underlying tool did not run successfully — this gate cannot "
        "certify anything about this diff and must not be treated as a pass.",
        file=sys.stderr,
    )
    return 1
