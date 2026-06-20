"""Unit tests for profile path-traversal defence (Task 1).

Run from the plugin root:
    python -m pytest tests/test_path_traversal.py
or without pytest:
    python tests/test_path_traversal.py
"""
import os
import sys
import tempfile
import importlib.util

# Import the dep-free resolver directly by file path so the test does not pull
# in torch / comfy (which _shared.py imports at module level).
_HERE = os.path.dirname(os.path.abspath(__file__))
_PATHS_FILE = os.path.join(_HERE, "..", "nodes", "image", "factory", "_paths.py")
_spec = importlib.util.spec_from_file_location("_misaka_paths", _PATHS_FILE)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
resolve_profile_path = _mod.resolve_profile_path


def _base():
    return tempfile.mkdtemp(prefix="misaka_profiles_")


def test_simple_name_ok():
    base = _base()
    p = resolve_profile_path(base, "modelA/my_profile")
    assert os.path.realpath(p).startswith(os.path.realpath(base))
    assert p.endswith(".json")


def test_relative_traversal_rejected():
    base = _base()
    for bad in ["../../x", "..\\..\\x", "foo/../../bar", "../secret"]:
        try:
            resolve_profile_path(base, bad)
        except ValueError:
            continue
        raise AssertionError(f"traversal not rejected: {bad!r}")


def test_absolute_path_rejected():
    base = _base()
    # Absolute paths must not be allowed to escape the storage root.
    abs_candidates = ["/etc/passwd", "C:\\Windows\\system32\\x", "D:\\secret\\x"]
    for bad in abs_candidates:
        # os.path.join(base, abs) returns the abs path on its own platform,
        # which then fails the commonpath check → ValueError.
        try:
            resolved = resolve_profile_path(base, bad)
        except ValueError:
            continue
        # On platforms where the join did NOT absolutise (e.g. a Windows path on
        # POSIX), the result must still be confined to base.
        assert os.path.realpath(resolved).startswith(os.path.realpath(base)), \
            f"absolute path escaped base: {bad!r} -> {resolved!r}"


def test_null_byte_rejected():
    base = _base()
    try:
        resolve_profile_path(base, "foo\x00bar")
    except ValueError:
        return
    raise AssertionError("null byte not rejected")


def test_none_rejected():
    base = _base()
    try:
        resolve_profile_path(base, None)
    except ValueError:
        return
    raise AssertionError("None not rejected")


if __name__ == "__main__":
    failures = 0
    for fn in [v for k, v in sorted(globals().items()) if k.startswith("test_")]:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL {fn.__name__}: {e}")
    print(f"\n{('ALL PASSED' if not failures else str(failures) + ' FAILED')}")
    sys.exit(1 if failures else 0)
