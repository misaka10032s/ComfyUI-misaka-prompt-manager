"""Unit tests for profile path-traversal defence (Task 1 + node-save follow-up).

Run from the plugin root:
    python -m pytest tests/test_path_traversal.py
or without pytest:
    python tests/test_path_traversal.py
"""
import os
import sys
import types
import tempfile
import importlib
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


# ---------------------------------------------------------------------------
# Node-save coverage: MisakaImageProfileFactory.execute()'s save_as_profile
# write (nodes/image/factory/profile_factory.py). The REST routes were fixed
# via resolve_profile_path() in cab4ac0; this node-based save path was missed
# (BP-IMG-1). ComfyUI's runtime deps (folder_paths, comfy.sd/comfy.utils) are
# stubbed out so the node can be imported and driven without a real ComfyUI
# install; torch stays real (already a plugin dependency).
# ---------------------------------------------------------------------------

def _load_profile_factory_module():
    plugin_root = os.path.abspath(os.path.join(_HERE, ".."))
    if plugin_root not in sys.path:
        sys.path.insert(0, plugin_root)

    if "folder_paths" not in sys.modules:
        fp = types.ModuleType("folder_paths")
        fp.get_filename_list = lambda *a, **k: []
        fp.get_full_path = lambda *a, **k: None
        fp.get_folder_paths = lambda *a, **k: []
        sys.modules["folder_paths"] = fp

    if "comfy" not in sys.modules:
        comfy_mod = types.ModuleType("comfy")
        comfy_sd = types.ModuleType("comfy.sd")
        comfy_utils = types.ModuleType("comfy.utils")
        comfy_sd.load_checkpoint_guess_config = lambda *a, **k: (None, None, None)
        comfy_sd.load_lora_for_models = lambda *a, **k: (None, None)
        comfy_utils.load_torch_file = lambda *a, **k: None
        comfy_mod.sd = comfy_sd
        comfy_mod.utils = comfy_utils
        sys.modules["comfy"] = comfy_mod
        sys.modules["comfy.sd"] = comfy_sd
        sys.modules["comfy.utils"] = comfy_utils

    return importlib.import_module("nodes.image.factory.profile_factory")


def _run_node_save(base, save_as_profile):
    """Drive execute() far enough to hit the save_as_profile write. The
    model-loading tail (apply_assets) is expected to fail with the stubbed
    deps (no real checkpoint) — that happens AFTER the save block, so it is
    swallowed here; only the file-write side effect is under test."""
    factory_mod = _load_profile_factory_module()
    factory_mod.get_storage_path = lambda: base
    node = factory_mod.MisakaImageProfileFactory()
    try:
        node.execute(
            checkpoint=None, character="", H="", expression="",
            pose="", scene="", output_name="out", save_as_profile=save_as_profile,
            clip_skip=0,
        )
    except Exception:
        pass


def test_node_save_traversal_rejected():
    sandbox = tempfile.mkdtemp(prefix="misaka_node_save_")
    base = os.path.join(sandbox, "storage")
    os.makedirs(base)

    for bad in ["../escaped", "..\\escaped", "../../escaped"]:
        escape_target = os.path.join(sandbox, "escaped.json")
        if os.path.exists(escape_target):
            os.remove(escape_target)

        _run_node_save(base, bad)

        assert not os.path.exists(escape_target), \
            f"node save escaped storage root: {bad!r} -> {escape_target!r}"
        # nothing should have landed outside `base` either
        for root, _dirs, files in os.walk(sandbox):
            if root == base or root.startswith(base + os.sep):
                continue
            assert not files, f"unexpected file(s) outside base for {bad!r}: {files} in {root}"


def test_node_save_normal_name_still_saves():
    sandbox = tempfile.mkdtemp(prefix="misaka_node_save_")
    base = os.path.join(sandbox, "storage")
    os.makedirs(base)

    _run_node_save(base, "my_profile")

    expected = os.path.join(base, "my_profile.json")
    assert os.path.exists(expected), f"expected profile not saved at {expected!r}"


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
