"""Runtime write guard (determinism gate G3(c), pattern P9).

A test that writes under the repository root, outside the system temp folder, leaves a file behind
that the next run can read, so its result can differ between runs. The static checker
(`quality-gates/check_test_determinism.py`) cannot see a write made by product code that a test
calls, so this guard watches the writes themselves and refuses such a write.

It is a `sys.addaudithook` hook: the interpreter itself reports every file open for writing, remove,
rename, mkdir, rmdir, truncate, symlink, link, copy, move and sqlite3 connect BEFORE it happens,
whatever name the caller bound the function to (`from os import remove` before the fixture ran,
`io.open`, `os.open`, `io.FileIO`, `tarfile.open`). While the guard is active, a target inside the
repo root and outside the system temp folder fails the test with `RepoWriteError`, and is also
recorded: product code that swallows the exception still turns the test red at its end. An audit
hook cannot be removed, so it is installed once and does nothing while the flag is off.
`cv2.imwrite` writes from C++ and raises no audit event, so it alone is patched, when `cv2` is
importable.

Allowed inside the repo: the runner's own outputs (`.pytest_cache`, `__pycache__`, `.coverage*`,
`coverage.xml`, `htmlcov`). Everything under `tempfile.gettempdir()` is allowed.
"""
import functools
import importlib.util
import os
import sys
import tempfile
from pathlib import Path
from urllib.parse import unquote

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_TEMP_ROOT = Path(tempfile.gettempdir()).resolve()
_ALLOWED_DIR_NAMES = {".pytest_cache", "__pycache__", "htmlcov"}
_WRITE_MODE_CHARS = frozenset("wax+")
_WRITE_OS_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC

# audit event -> the argument positions that name a target path (os.replace raises os.rename; os.unlink raises
# os.remove; os.makedirs and os.removedirs raise os.mkdir / os.remove / os.rmdir; shutil.copy and copy2 raise
# shutil.copyfile; Path.write_text and Path.touch go through `open`).
_AUDIT_TARGETS = {
    "os.remove": (0,),
    "os.rename": (0, 1),
    "os.mkdir": (0,),
    "os.rmdir": (0,),
    "os.truncate": (0,),
    "os.symlink": (1,),
    "os.link": (1,),
    "shutil.rmtree": (0,),
    "shutil.copyfile": (1,),
    "shutil.copytree": (1,),
    "shutil.move": (0, 1),
}


class RepoWriteError(AssertionError):
    """A test (or the product code it calls) wrote under the repo root, outside the temp folder."""


class _WriteGuard:
    """The guard's state, read by the audit hook."""

    active = False
    installed = False
    violations: list[str] = []


def _inside(path, root):
    return path == root or root in path.parents


def _is_repo_write(target):
    """The resolved path when `target` is inside the repo root, outside the temp folder and not a runner output."""
    if target is None or isinstance(target, int):  # nothing to resolve, or a descriptor opened elsewhere
        return None
    try:
        raw = os.fsdecode(target)
    except (TypeError, ValueError):
        return None
    if raw in ("", ":memory:"):
        return None
    if raw.startswith("file:"):
        raw = unquote(raw[len("file:"):].split("?", 1)[0])
    resolved = Path(os.path.abspath(raw)).resolve()
    if _inside(resolved, _TEMP_ROOT) or not _inside(resolved, _REPO_ROOT):
        return None
    parts = resolved.relative_to(_REPO_ROOT).parts
    if any(part in _ALLOWED_DIR_NAMES for part in parts):
        return None
    if parts and (parts[-1].startswith(".coverage") or parts[-1] == "coverage.xml"):
        return None
    return resolved


def _check(target, action):
    resolved = _is_repo_write(target)
    if resolved is None:
        return
    message = f"{action} writes inside the repo outside the temp folder: {resolved}"
    _WriteGuard.violations.append(message)
    raise RepoWriteError(message)


def _sqlite_file(database):
    """The file a sqlite3.connect() argument names, or None for an in-memory database."""
    if not isinstance(database, (str, bytes, os.PathLike)):
        return None
    text = os.fsdecode(database)
    return None if text in ("", ":memory:") else text


def _audit_hook(event, args):
    if not _WriteGuard.active:
        return
    if event == "open":
        path, mode, flags = args
        # os.open passes mode None and the real flags; io.FileIO (behind open, io.open, tarfile.open) passes its
        # mode string with the flags it derived from it
        writing = (isinstance(flags, int) and flags & _WRITE_OS_FLAGS) or (
            mode is not None and _WRITE_MODE_CHARS & set(str(mode))
        )
        if writing:
            _check(path, "os.open" if mode is None else "open")
    elif event == "sqlite3.connect":
        _check(_sqlite_file(args[0]), "sqlite3.connect")
    elif event in _AUDIT_TARGETS:
        for position in _AUDIT_TARGETS[event]:
            if position < len(args):
                _check(args[position], event)


def _patch_cv2_imwrite():
    """cv2.imwrite writes from C++ and raises no audit event. Returns the function that undoes the patch."""
    if importlib.util.find_spec("cv2") is None:
        return lambda: None
    import cv2

    original = cv2.imwrite

    @functools.wraps(original)
    def guarded(filename, *args, **kwargs):
        _check(filename, "cv2.imwrite")
        return original(filename, *args, **kwargs)

    cv2.imwrite = guarded

    def restore():
        cv2.imwrite = original

    return restore


@pytest.fixture(scope="session", autouse=True)
def _guard_repo_writes():
    if not _WriteGuard.installed:
        sys.addaudithook(_audit_hook)
        _WriteGuard.installed = True
    restore_cv2 = _patch_cv2_imwrite()
    _WriteGuard.active = True
    try:
        yield
    finally:
        _WriteGuard.active = False
        restore_cv2()


@pytest.fixture(autouse=True)
def _fail_on_swallowed_repo_write():
    """A write refused by the guard that product code caught and swallowed still fails the test."""
    _WriteGuard.violations = []
    yield
    if _WriteGuard.violations:
        pytest.fail("write to the repo root outside the temp folder: " + "; ".join(_WriteGuard.violations))
