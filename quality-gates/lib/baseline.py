"""Generic version-controlled baseline-diff helper, shared by every gate that needs
"fail only on NEW findings relative to what already existed on this tree" (G1 ruff, G2 mypy).

Ported from learningMachine's Python-family quality-gates recipe (api/quality-gates/lib/
baseline.py) — this repo is L0-only (see quality-gates/run.py docstring), so only the two
callers above exist here; there is no G4/G5/G6 in this recipe.

A baseline is a JSON array of violation *identity strings* — a stable key built by the
caller from fields that survive line drift (e.g. "relative/file.py|CODE|message text"),
deliberately EXCLUDING the line number so a violation that merely moved a few lines because
of an unrelated edit above it doesn't register as "new". Two violations with the same
identity are indistinguishable and collapse to one baseline entry — acceptable for this
recipe's scale (a few dozen pre-existing findings, not hundreds).
"""
from __future__ import annotations

import json
from pathlib import Path


def load(path: Path) -> list[str]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, violations: list[str]) -> None:
    path.write_text(json.dumps(sorted(set(violations)), indent=2) + "\n", encoding="utf-8")


def diff(current: list[str], baseline: list[str]) -> tuple[list[str], list[str]]:
    """Returns (new_violations, resolved_violations), both sorted.

    new = present now, absent from the baseline (blocks the gate).
    resolved = present in the baseline, absent now (NOT automatically good news — see the
    vanished-baseline-as-FAIL handling in each check_*_baseline.py caller; a resolved entry
    can mean a genuine fix, OR that the underlying tool silently stopped seeing it).
    """
    baseline_set = set(baseline)
    current_set = set(current)
    new = sorted(v for v in current if v not in baseline_set)
    resolved = sorted(v for v in baseline if v not in current_set)
    return new, resolved
