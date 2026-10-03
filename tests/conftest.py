"""Runtime write guard (determinism gate G3(c), pattern P9).

A test that writes under the repository root, outside the system temp folder, leaves a file behind
that the next run can read, so its result can differ between runs. The static checker
(`quality-gates/check_test_determinism.py`) cannot see a write made by product code that a test
calls, so this session fixture wraps the file-system write functions and refuses such a write.

Allowed inside the repo: the runner's own outputs (`.pytest_cache`, `__pycache__`, `.coverage*`,
`coverage.xml`, `htmlcov`). Everything under `tempfile.gettempdir()` is allowed.
"""
import builtins
import functools
import io
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path
from urllib.parse import unquote

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_TEMP_ROOT = Path(tempfile.gettempdir()).resolve()
_ALLOWED_DIR_NAMES = {".pytest_cache", "__pycache__", "htmlcov"}
_WRITE_OPEN_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC

_violations = []


class RepoWriteError(AssertionError):
    """A test (or the product code it calls) wrote under the repo root, outside the temp folder."""


def _inside(path, root):
    return path == root or root in path.parents


def _check(target, action):
    if target is None or isinstance(target, int):
        return
    try:
        raw = os.fsdecode(target)
    except TypeError:
        return
    if raw in ("", ":memory:"):
        return
    if raw.startswith("file:"):
        raw = unquote(raw[len("file:"):].split("?", 1)[0])
    resolved = Path(os.path.abspath(raw)).resolve()
    if _inside(resolved, _TEMP_ROOT) or not _inside(resolved, _REPO_ROOT):
        return
    parts = resolved.relative_to(_REPO_ROOT).parts
    if any(part in _ALLOWED_DIR_NAMES for part in parts):
        return
    if parts and (parts[-1].startswith(".coverage") or parts[-1] == "coverage.xml"):
        return
    message = f"{action} writes inside the repo outside the temp folder: {resolved}"
    _violations.append(message)
    raise RepoWriteError(message)


def _wrap_function(original, label, positions, keywords):
    @functools.wraps(original)
    def guarded(*args, **kwargs):
        for index in positions:
            if index < len(args):
                _check(args[index], label)
        for key in keywords:
            if key in kwargs:
                _check(kwargs[key], label)
        return original(*args, **kwargs)

    return guarded


def _wrap_open(original):
    @functools.wraps(original)
    def guarded(*args, **kwargs):
        mode = args[1] if len(args) > 1 else kwargs.get("mode", "r")
        if isinstance(mode, str) and any(char in mode for char in "wax+"):
            _check(args[0] if args else kwargs.get("file"), "open")
        return original(*args, **kwargs)

    return guarded


def _wrap_os_open(original):
    @functools.wraps(original)
    def guarded(*args, **kwargs):
        flags = args[1] if len(args) > 1 else kwargs.get("flags", 0)
        if isinstance(flags, int) and flags & _WRITE_OPEN_FLAGS:
            _check(args[0] if args else kwargs.get("path"), "os.open")
        return original(*args, **kwargs)

    return guarded


def _wrap_path_method(original, label, other_positions, other_keywords):
    @functools.wraps(original)
    def guarded(self, *args, **kwargs):
        _check(self, label)
        for index in other_positions:
            if index < len(args):
                _check(args[index], label)
        for key in other_keywords:
            if key in kwargs:
                _check(kwargs[key], label)
        return original(self, *args, **kwargs)

    return guarded


# (module, function name, positional indexes that are write targets, keyword names that are)
_FUNCTION_TARGETS = (
    (os, "remove", (0,), ("path",)),
    (os, "unlink", (0,), ("path",)),
    (os, "rename", (0, 1), ("src", "dst")),
    (os, "replace", (0, 1), ("src", "dst")),
    (os, "makedirs", (0,), ("name",)),
    (os, "mkdir", (0,), ("path",)),
    (os, "rmdir", (0,), ("path",)),
    (os, "removedirs", (0,), ("name",)),
    (os, "truncate", (0,), ("path",)),
    (shutil, "rmtree", (0,), ("path",)),
    (shutil, "copy", (1,), ("dst",)),
    (shutil, "copy2", (1,), ("dst",)),
    (shutil, "copyfile", (1,), ("dst",)),
    (shutil, "copytree", (1,), ("dst",)),
    (shutil, "move", (0, 1), ("src", "dst")),
    (sqlite3, "connect", (0,), ("database",)),
)

# (Path method name, positional indexes of a second path that is also written, its keyword names)
_PATH_METHODS = (
    ("write_text", (), ()),
    ("write_bytes", (), ()),
    ("mkdir", (), ()),
    ("touch", (), ()),
    ("unlink", (), ()),
    ("rmdir", (), ()),
    ("rename", (0,), ("target",)),
    ("replace", (0,), ("target",)),
    ("symlink_to", (), ()),
    ("hardlink_to", (), ()),
)


@pytest.fixture(scope="session", autouse=True)
def _guard_repo_writes():
    patcher = pytest.MonkeyPatch()
    patcher.setattr(builtins, "open", _wrap_open(builtins.open))
    patcher.setattr(io, "open", _wrap_open(io.open))
    patcher.setattr(os, "open", _wrap_os_open(os.open))
    for module, name, positions, keywords in _FUNCTION_TARGETS:
        patcher.setattr(
            module,
            name,
            _wrap_function(getattr(module, name), f"{module.__name__}.{name}", positions, keywords),
        )
    for name, positions, keywords in _PATH_METHODS:
        original = getattr(Path, name)
        patcher.setattr(Path, name, _wrap_path_method(original, f"Path.{name}", positions, keywords))
    yield
    patcher.undo()


@pytest.fixture(autouse=True)
def _fail_on_swallowed_repo_write():
    """A write refused by the guard that product code caught and swallowed still fails the test."""
    _violations.clear()
    yield
    if _violations:
        pytest.fail("write to the repo root outside the temp folder: " + "; ".join(_violations))
