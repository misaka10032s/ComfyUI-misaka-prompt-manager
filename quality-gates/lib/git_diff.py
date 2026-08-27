"""Shared diff-scoping helper for G3b (assertion-presence on new/changed tests). Ported from
learningMachine's Python-family recipe (api/quality-gates/lib/git_diff.py) — kept in sync in
spirit, trimmed to only what G3b needs (this repo has no G5/G6 diff-coverage/mutation gates).

Scope model (same as the source recipe, deliberately simple): the base ref is the merge-base
with ``master`` (this repo's default branch), and "changed" means "working tree right now vs
that merge base" (``git diff <base>``, no upper bound) — covers committed-on-branch, staged,
AND unstaged-but-tracked changes in one pass. Override with ``QUALITY_BASE_REF`` for a
narrower/explicit comparison.

Known gap (inherited from the source recipe): a brand-new file that has never been `git add`-ed
is invisible to plain ``git diff <base>`` (untracked, not "unstaged") — this helper does not add
``--others``/``--include-untracked``. Self-heals once the file is staged (this cluster always
stages before a gate/commit run), so left as-is rather than silently inaccurate.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

MAIN_BRANCH = "master"  # this repo's default branch (git branch --show-current == master).


def ensure_utf8_stdio() -> None:
    """Windows consoles default to a legacy codepage (cp950/cp1252), which raises/garbles on
    the em-dashes this recipe's own gate messages use. Every gate entrypoint calls this first."""
    import sys

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure") and (stream.encoding or "").lower() != "utf-8":
            stream.reconfigure(encoding="utf-8", errors="replace")


def _git(args: list[str], cwd: Path) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True, encoding="utf-8"
    ).stdout


def resolve_base_ref(cwd: Path) -> str:
    """Resolve the base ref to diff against."""
    override = os.environ.get("QUALITY_BASE_REF", "").strip()
    if override:
        return override
    try:
        base = _git(["merge-base", "HEAD", MAIN_BRANCH], cwd).strip()
        if base:
            return base
    except subprocess.CalledProcessError:
        pass  # `master` not reachable (e.g. detached/shallow) — fall through.
    try:
        return _git(["rev-parse", "HEAD~1"], cwd).strip()
    except subprocess.CalledProcessError:
        return _git(["rev-parse", "HEAD"], cwd).strip()  # single-commit repo: empty diff


def repo_prefix(cwd: Path) -> str:
    """git's own prefix for `cwd` relative to the repo top-level, e.g. "quality-gates/"."""
    return _git(["rev-parse", "--show-prefix"], cwd).strip()


def _strip_prefix(path: str, prefix: str) -> str:
    return path[len(prefix):] if prefix and path.startswith(prefix) else path


def get_changed_files(cwd: Path, base_ref: str, extensions: list[str]) -> list[str]:
    """Changed files (added/copied/modified/renamed — never deleted) under `cwd`, filtered
    to the given extensions, returned as paths relative to `cwd`."""
    prefix = repo_prefix(cwd)
    patterns = [f"*.{ext}" for ext in extensions]
    out = _git(["diff", "--name-only", "--diff-filter=ACMR", base_ref, "--", *patterns], cwd)
    return [
        _strip_prefix(line.strip().replace("\\", "/"), prefix)
        for line in out.split("\n")
        if line.strip()
    ]


def get_changed_line_ranges(
    cwd: Path, base_ref: str, files: list[str]
) -> dict[str, set[int]]:
    """Map[relPath, set[lineNumber]] of lines added/changed on the "new" side for the given
    files. Pure deletions contribute no lines (nothing new to require assertions for)."""
    result: dict[str, set[int]] = {}
    if not files:
        return result
    prefix = repo_prefix(cwd)
    hunk_re = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
    diff_out = _git(["diff", "--unified=0", "--diff-filter=ACMR", base_ref, "--", *files], cwd)
    current_file: str | None = None
    for line in diff_out.split("\n"):
        if line.startswith("+++ "):
            raw = line[4:].strip()
            if raw == "/dev/null":
                current_file = None
                continue
            cleaned = _strip_prefix(re.sub(r"^b/", "", raw).replace("\\", "/"), prefix)
            current_file = cleaned
            result.setdefault(current_file, set())
            continue
        if line.startswith("@@ ") and current_file:
            m = hunk_re.match(line)
            if m:
                start_line = int(m.group(1))
                count = 1 if m.group(2) is None else int(m.group(2))
                for i in range(count):
                    result[current_file].add(start_line + i)
    return result
