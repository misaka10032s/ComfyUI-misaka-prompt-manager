"""
Torch-free unit tests for the RVC safe-load decision logic (voice/_safe_load.py).

Loads the module under test directly by file path (bypassing `voice/__init__.py`,
which imports `rvc_wrapper` -> `torch` at package-import time) so these tests can
run under this plugin's own quality-gate interpreter (py -3.11), which has no
torch installed at all. `torch` itself is faked via `sys.modules` injection so
we can assert exactly what the loader passes to `torch.load` / `torch.serialization
.safe_globals`, without needing real torch anywhere in this file.

Run from the plugin root (matches quality-gates/run.py g3's own invocation):
    py -3.11 -m pytest -q --rootdir=. --confcutdir=. test_rvc_safe_load.py
    (cwd=tests/)
"""
import importlib.util
import logging
import os
import pickle
import sys
import types

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_MODULE_FILE = os.path.join(_HERE, "..", "voice", "_safe_load.py")


def _load_module_under_test():
    spec = importlib.util.spec_from_file_location("_misaka_safe_load", _MODULE_FILE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _FakeSafeGlobalsCtx:
    """Stands in for `torch.serialization.safe_globals(...)` — a no-op context
    manager here, just records what it was called with."""

    def __init__(self, globals_list):
        self.globals_list = globals_list

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _install_fake_torch(monkeypatch, effects):
    """
    Install a fake `torch` module into sys.modules so `import torch` inside
    `load_checkpoint()` binds to it instead of touching disk / a real torch.

    This fake torch does NOT define `get_unsafe_globals_in_checkpoint`, so
    `load_checkpoint()` takes the fallback-of-last-resort branch (module
    docstring step 4 / `_load_via_exception_heuristic`) — the decision is
    made by catching the exception `torch.load()` raises, exactly like torch
    < 2.4 would behave. See `_install_fake_torch_with_static_scan` below for
    the current-torch static-scan decision path (module docstring steps 1-3).

    `effects`: list consumed in call order by successive `torch.load()` calls
    — each entry is either the value to return, or an Exception instance to
    raise from that call.
    """
    calls = []
    fake_torch = types.ModuleType("torch")

    def fake_load(path, map_location=None, weights_only=None):
        calls.append(
            {"path": path, "map_location": map_location, "weights_only": weights_only}
        )
        effect = effects.pop(0)
        if isinstance(effect, BaseException):
            raise effect
        return effect

    fake_torch.load = fake_load
    fake_torch.serialization = types.SimpleNamespace(
        safe_globals=lambda gl: _FakeSafeGlobalsCtx(gl)
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    return calls


def _install_fake_torch_with_static_scan(monkeypatch, scan_effect, load_effects):
    """
    Like `_install_fake_torch`, but the fake torch ALSO defines
    `get_unsafe_globals_in_checkpoint`, so `load_checkpoint()` takes the
    current, torch>=2.4 static-scan decision path (module docstring steps
    1-3; 待回答 #49 review F1) instead of the exception-based fallback of
    last resort.

    `scan_effect`: the value `get_unsafe_globals_in_checkpoint(path)` returns
      (a list of unsafe-global name strings), or an Exception instance it
      raises instead (simulating a corrupt/garbage/missing file — the static
      scan itself fails before any `torch.load()` call is ever made).
    `load_effects`: same shape as `_install_fake_torch`'s `effects`, consumed
      by successive `torch.load()` calls.
    """
    calls = []
    fake_torch = types.ModuleType("torch")

    def fake_load(path, map_location=None, weights_only=None):
        calls.append(
            {"path": path, "map_location": map_location, "weights_only": weights_only}
        )
        effect = load_effects.pop(0)
        if isinstance(effect, BaseException):
            raise effect
        return effect

    def fake_scan(path):
        if isinstance(scan_effect, BaseException):
            raise scan_effect
        return scan_effect

    fake_torch.load = fake_load
    fake_torch.serialization = types.SimpleNamespace(
        safe_globals=lambda gl: _FakeSafeGlobalsCtx(gl),
        get_unsafe_globals_in_checkpoint=fake_scan,
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    return calls


@pytest.fixture()
def safe_load(monkeypatch):
    monkeypatch.delenv("MISAKA_PM_RVC_STRICT_LOAD", raising=False)
    return _load_module_under_test()


def test_safe_path_attempted_first_with_weights_only_true(safe_load, monkeypatch):
    calls = _install_fake_torch(monkeypatch, effects=[{"weight": "ok"}])

    result = safe_load.load_checkpoint("model.pth", safe_globals=[str])

    assert result == {"weight": "ok"}
    assert len(calls) == 1
    assert calls[0]["weights_only"] is True
    assert calls[0]["map_location"] == "cpu"
    assert calls[0]["path"] == "model.pth"


def test_safe_path_success_needs_no_fallback_and_no_warning(safe_load, monkeypatch, caplog, capsys):
    _install_fake_torch(monkeypatch, effects=[{"weight": "ok"}])
    caplog.set_level(logging.WARNING)

    safe_load.load_checkpoint("model.pth")

    assert not any(rec.levelno >= logging.WARNING for rec in caplog.records)
    assert capsys.readouterr().out == ""


def test_fallback_used_with_warning_on_unpickling_error(safe_load, monkeypatch, caplog, capsys):
    calls = _install_fake_torch(
        monkeypatch,
        effects=[
            pickle.UnpicklingError("Weights only load failed: GLOBAL x not allowed"),
            {"weight": "fallback-ok"},
        ],
    )
    caplog.set_level(logging.WARNING)

    result = safe_load.load_checkpoint("model.pth")

    assert result == {"weight": "fallback-ok"}
    assert len(calls) == 2
    assert calls[0]["weights_only"] is True
    assert calls[1]["weights_only"] is False
    assert any(rec.levelno == logging.WARNING for rec in caplog.records)
    assert "model.pth" in caplog.text
    assert "model.pth" in capsys.readouterr().out


def test_fallback_used_on_runtime_error(safe_load, monkeypatch, caplog):
    calls = _install_fake_torch(
        monkeypatch,
        effects=[RuntimeError("Unsupported global"), {"weight": "fallback-ok"}],
    )
    caplog.set_level(logging.WARNING)

    result = safe_load.load_checkpoint("model.pth")

    assert result == {"weight": "fallback-ok"}
    assert len(calls) == 2
    assert any(rec.levelno == logging.WARNING for rec in caplog.records)


def test_strict_mode_raises_and_never_calls_unsafe_path(safe_load, monkeypatch):
    monkeypatch.setenv("MISAKA_PM_RVC_STRICT_LOAD", "1")
    calls = _install_fake_torch(
        monkeypatch, effects=[pickle.UnpicklingError("Weights only load failed")]
    )

    with pytest.raises(RuntimeError):
        safe_load.load_checkpoint("model.pth")

    assert len(calls) == 1  # only the safe attempt — fallback (weights_only=False) never ran


def test_strict_mode_off_by_default(safe_load):
    assert safe_load.strict_mode_enabled() is False


def test_non_pickle_exception_propagates_without_fallback(safe_load, monkeypatch):
    calls = _install_fake_torch(monkeypatch, effects=[FileNotFoundError("nope")])

    with pytest.raises(FileNotFoundError):
        safe_load.load_checkpoint("missing.pth")

    assert len(calls) == 1  # no fallback attempted for a non-weights_only failure


# ---------------------------------------------------------------------------
# 待回答 #49 review F1 — static-scan decision path (torch>=2.4).
#
# The previous decision logic caught pickle.UnpicklingError/RuntimeError from
# a first weights_only=True attempt, which also caught plain file corruption
# (a truncated/garbage file raises the same exception types) and fired the
# "this may run arbitrary code" warning on a merely damaged file — contrary
# to this module's own documented contract. The fix scans the checkpoint
# STATICALLY first via torch.serialization.get_unsafe_globals_in_checkpoint;
# these tests assert the four required outcomes: a corrupt/garbage file
# raises with NO torch.load call and NO warning, a clean checkpoint takes
# exactly one weights_only=True call, and a checkpoint needing an unsafe
# global takes exactly one weights_only=False call after warning.
# ---------------------------------------------------------------------------


def test_static_scan_clean_checkpoint_uses_safe_path_only(safe_load, monkeypatch, caplog, capsys):
    calls = _install_fake_torch_with_static_scan(
        monkeypatch, scan_effect=[], load_effects=[{"weight": "ok"}]
    )
    caplog.set_level(logging.WARNING)

    result = safe_load.load_checkpoint("model.pth", safe_globals=[str])

    assert result == {"weight": "ok"}
    assert [c["weights_only"] for c in calls] == [True]
    assert not any(rec.levelno >= logging.WARNING for rec in caplog.records)
    assert capsys.readouterr().out == ""


def test_static_scan_truncated_archive_raises_without_fallback_or_warning(
    safe_load, monkeypatch, caplog, capsys
):
    calls = _install_fake_torch_with_static_scan(
        monkeypatch,
        scan_effect=RuntimeError(
            "PytorchStreamReader failed reading zip archive: failed finding "
            "central directory"
        ),
        load_effects=[],
    )
    caplog.set_level(logging.WARNING)

    with pytest.raises(RuntimeError):
        safe_load.load_checkpoint("truncated.pth")

    assert [c["weights_only"] for c in calls] == []  # torch.load never called
    assert not any(rec.levelno >= logging.WARNING for rec in caplog.records)
    assert capsys.readouterr().out == ""


def test_static_scan_garbage_bytes_raises_without_fallback_or_warning(
    safe_load, monkeypatch, caplog, capsys
):
    calls = _install_fake_torch_with_static_scan(
        monkeypatch,
        scan_effect=ValueError("Expected input to be a checkpoint returned by torch.save"),
        load_effects=[],
    )
    caplog.set_level(logging.WARNING)

    with pytest.raises(ValueError):
        safe_load.load_checkpoint("garbage.pth")

    assert [c["weights_only"] for c in calls] == []  # torch.load never called
    assert not any(rec.levelno >= logging.WARNING for rec in caplog.records)
    assert capsys.readouterr().out == ""


def test_static_scan_unsafe_global_falls_back_with_warning(
    safe_load, monkeypatch, caplog, capsys
):
    calls = _install_fake_torch_with_static_scan(
        monkeypatch,
        scan_effect=["some.fork.Global"],
        load_effects=[{"weight": "fallback-ok"}],
    )
    caplog.set_level(logging.WARNING)

    result = safe_load.load_checkpoint("model.pth")

    assert result == {"weight": "fallback-ok"}
    assert [c["weights_only"] for c in calls] == [False]  # no safe attempt — scan already decided
    assert any(rec.levelno == logging.WARNING for rec in caplog.records)
    assert "model.pth" in caplog.text
    assert "some.fork.Global" in caplog.text
    assert "model.pth" in capsys.readouterr().out


def test_static_scan_strict_mode_raises_listing_unsafe_globals(safe_load, monkeypatch):
    monkeypatch.setenv("MISAKA_PM_RVC_STRICT_LOAD", "1")
    calls = _install_fake_torch_with_static_scan(
        monkeypatch, scan_effect=["some.fork.Global"], load_effects=[]
    )

    with pytest.raises(RuntimeError, match="some.fork.Global"):
        safe_load.load_checkpoint("model.pth")

    assert calls == []  # neither the safe nor the unsafe torch.load is ever called


@pytest.mark.parametrize("raw,expected", [
    ("1", True), ("true", True), ("TRUE", True), ("Yes", True), ("on", True),
    ("0", False), ("false", False), ("", False), ("2", False), ("no", False),
])
def test_strict_mode_accepts_truthy_spellings_case_insensitively(safe_load, monkeypatch, raw, expected):
    # 待回答 #49 review F7 — previously only the exact string "1" was accepted.
    monkeypatch.setenv("MISAKA_PM_RVC_STRICT_LOAD", raw)
    assert safe_load.strict_mode_enabled() is expected
