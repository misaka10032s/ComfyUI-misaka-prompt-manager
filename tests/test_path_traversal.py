"""Unit tests for profile path-traversal defence (Task 1 + node-save follow-up).

Run from the plugin root:
    python -m pytest tests/test_path_traversal.py
"""
import os
import sys
import types
import importlib
import importlib.util

import pytest

# Import the dep-free resolver directly by file path so the test does not pull
# in torch / comfy (which _shared.py imports at module level).
_HERE = os.path.dirname(os.path.abspath(__file__))
_PATHS_FILE = os.path.join(_HERE, "..", "nodes", "image", "factory", "_paths.py")
_spec = importlib.util.spec_from_file_location("_misaka_paths", _PATHS_FILE)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
resolve_profile_path = _mod.resolve_profile_path


def test_simple_name_ok(tmp_path):
    base = str(tmp_path)
    p = resolve_profile_path(base, "modelA/my_profile")
    assert os.path.realpath(p).startswith(os.path.realpath(base))
    assert p.endswith(".json")


def test_relative_traversal_rejected(tmp_path):
    base = str(tmp_path)
    for bad in ["../../x", "..\\..\\x", "foo/../../bar", "../secret"]:
        with pytest.raises(ValueError):
            resolve_profile_path(base, bad)


def test_absolute_path_rejected(tmp_path):
    base = str(tmp_path)
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


def test_null_byte_rejected(tmp_path):
    base = str(tmp_path)
    with pytest.raises(ValueError):
        resolve_profile_path(base, "foo\x00bar")


def test_none_rejected(tmp_path):
    base = str(tmp_path)
    with pytest.raises(ValueError):
        resolve_profile_path(base, None)


# ---------------------------------------------------------------------------
# Node-save coverage: MisakaImageProfileFactory.execute()'s save_as_profile
# write (nodes/image/factory/profile_factory.py). The REST routes were fixed
# via resolve_profile_path() in cab4ac0; this node-based save path was missed
# (BP-IMG-1). ComfyUI's runtime deps (folder_paths, comfy.sd/comfy.utils) are
# stubbed out so the node can be imported and driven without a real ComfyUI
# install; torch stays real (already a plugin dependency).
# ---------------------------------------------------------------------------

def _import_profile_factory_with_stubs():
    """Install the ComfyUI stubs, import profile_factory once (at collection,
    outside every test), then restore whatever sys.modules held before."""
    plugin_root = os.path.abspath(os.path.join(_HERE, ".."))
    if plugin_root not in sys.path:
        sys.path.insert(0, plugin_root)

    fp = types.ModuleType("folder_paths")
    fp.get_filename_list = lambda *a, **k: []
    fp.get_full_path = lambda *a, **k: None
    fp.get_folder_paths = lambda *a, **k: []

    comfy_mod = types.ModuleType("comfy")
    comfy_sd = types.ModuleType("comfy.sd")
    comfy_utils = types.ModuleType("comfy.utils")
    comfy_sd.load_checkpoint_guess_config = lambda *a, **k: (None, None, None)
    comfy_sd.load_lora_for_models = lambda *a, **k: (None, None)
    comfy_utils.load_torch_file = lambda *a, **k: None
    comfy_mod.sd = comfy_sd
    comfy_mod.utils = comfy_utils

    stubs = {
        "folder_paths": fp,
        "comfy": comfy_mod,
        "comfy.sd": comfy_sd,
        "comfy.utils": comfy_utils,
    }
    missing = object()
    saved = {name: sys.modules.get(name, missing) for name in stubs}
    sys.modules.update(stubs)
    try:
        return importlib.import_module("nodes.image.factory.profile_factory")
    finally:
        for name, old in saved.items():
            if old is missing:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old


profile_factory = _import_profile_factory_with_stubs()


def _run_node_save(monkeypatch, base, save_as_profile):
    """Drive execute() through the save_as_profile write. The model-loading
    tail (apply_assets) is replaced with a no-op returning its 5-tuple shape,
    so execute() runs to its end and any exception fails the test."""
    monkeypatch.setattr(profile_factory, "get_storage_path", lambda: base)
    monkeypatch.setattr(
        profile_factory, "apply_assets", lambda *a, **k: (None, None, None, None, None)
    )
    node = profile_factory.MisakaImageProfileFactory()
    node.execute(
        checkpoint=None, character="", H="", expression="",
        pose="", scene="", output_name="out", save_as_profile=save_as_profile,
        clip_skip=0,
    )


def test_node_save_traversal_rejected(tmp_path, monkeypatch):
    sandbox = str(tmp_path)
    base = os.path.join(sandbox, "storage")
    os.makedirs(base)

    for bad in ["../escaped", "..\\escaped", "../../escaped"]:
        escape_target = os.path.join(sandbox, "escaped.json")
        if os.path.exists(escape_target):
            os.remove(escape_target)

        _run_node_save(monkeypatch, base, bad)

        assert not os.path.exists(escape_target), \
            f"node save escaped storage root: {bad!r} -> {escape_target!r}"
        # nothing should have landed outside `base` either
        for root, _dirs, files in os.walk(sandbox):
            if root == base or root.startswith(base + os.sep):
                continue
            assert not files, f"unexpected file(s) outside base for {bad!r}: {files} in {root}"


def test_node_save_normal_name_still_saves(tmp_path, monkeypatch):
    sandbox = str(tmp_path)
    base = os.path.join(sandbox, "storage")
    os.makedirs(base)

    _run_node_save(monkeypatch, base, "my_profile")

    expected = os.path.join(base, "my_profile.json")
    assert os.path.exists(expected), f"expected profile not saved at {expected!r}"

