"""Shared "did mypy actually LOAD and HONOUR its own config" guard for G2
(`check_mypy_baseline.py`). Ported verbatim from learningMachine's Python-family recipe
(api/quality-gates/lib/mypy_config_guard.py, 2026-08-27 CROSS-REPO-mypy-failopen.md fix).

**Fail-open finding this closes:** mypy does not crash on a broken/missing config — it
silently falls back to defaults (losing whatever strictness/override table was configured),
still exits 0 or 1, and a bare exit-code guard (`subprocess_gate.run_with_exit_code_guard`,
`success_codes={0, 1}`) cannot tell that apart from a genuinely clean or genuinely-checked run.
Two independent, BOTH-required checks close this:

1. `verify_config_present()` — a ground-truth pre-flight check (config file exists, parses as
   TOML, contains a `[tool.mypy]` table) run BEFORE mypy is even invoked, against the SAME
   absolute path this gate passes via `--config-file=`. Catches the case where the config file
   is silently missing/gutted and mypy prints nothing about it at all.
2. `find_config_problem_lines()` — after running mypy with that explicit `--config-file=`,
   scans stdout+stderr (mypy's own config-parse complaints go to STDERR, not stdout) for
   mypy's own `<config-file>: [mypy...]: <message>` signature, restricted to lines that are
   NOT valid JSON (so a legitimate finding's `message` text can never be misread as a config
   problem — every genuine finding line IS valid JSON, so this pattern only ever runs against
   lines that already failed `json.loads`). Catches the case where mypy DOES complain but
   still limps along with SOME findings.

Passing an explicit ABSOLUTE `--config-file=` (rather than bare cwd-based auto-discovery) is
itself part of the fix: it turns "config file moved away" into mypy's own fatal `exit 2` /
"Cannot find config file" — already caught by `subprocess_gate`'s crash guard — instead of a
silent fallback to defaults.
"""
from __future__ import annotations

import re
import tomllib
from pathlib import Path

# Matches mypy's own config-parse-problem line, e.g.:
#   "pyproject.toml: [mypy]: Unrecognized option: not_a_real_mypy_option = True"
#   "D:/.../pyproject.toml: [mypy]: strict: Not a boolean: yes_please"
#   "D:/.../pyproject.toml: [mypy-nodes.*]: ..."  (per-module override sections)
# Deliberately anchored to the START of a line (`^`) and requires the line NOT be a JSON
# finding — every genuine finding line is valid JSON starting with "{", so this pattern is
# only ever evaluated against lines that already failed `json.loads`. That structurally rules
# out a legitimate finding's `message` text (which lives INSIDE a JSON string, never at
# column 0 of its own line) ever being misread as a config problem, even if that message text
# happened to contain a similar-looking substring.
_CONFIG_PROBLEM_RE = re.compile(r"^\S.*:\s*\[mypy(?:[.\-][\w.\-*]+)?\]:\s.+$")


def find_config_problem_lines(non_json_lines: list[str]) -> list[str]:
    """Scan lines mypy printed that were NOT parseable as a JSON finding (i.e. already
    filtered by the caller) for mypy's own config-parse-error signature. Returns every
    matching line verbatim (evidence for the FAIL message) — empty list if none found."""
    return [line for line in non_json_lines if _CONFIG_PROBLEM_RE.match(line.strip())]


def verify_config_present(config_path: Path) -> str | None:
    """Ground-truth pre-flight check, independent of mypy's own behaviour: confirms the
    config file this gate is ABOUT TO TELL mypy to use (via an explicit `--config-file=`)
    really exists, is parseable TOML, and actually contains a `[tool.mypy]` table.

    Returns None when OK, or a human-readable reason string when not — callers raise
    `GateToolCrashed` with that reason. This is what catches the "file present, section
    silently removed" state, which produces no stderr output at all for mypy to scan."""
    if not config_path.exists():
        return f"config file {config_path} does not exist"
    try:
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        return f"config file {config_path} is not valid TOML: {e}"
    if "mypy" not in data.get("tool", {}):
        return f"config file {config_path} has no [tool.mypy] table"
    return None
