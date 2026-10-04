"""
Real-torch tests for the RVC safe-load decision logic (voice/_safe_load.py).

This file imports torch directly: on an interpreter without torch it fails
loudly at collection instead of vanishing from the run. Run it with an
interpreter that has torch, e.g. the ComfyUI EMBEDDED interpreter:

    D:/AIprojects/ComfyUI_windows_portable/python_embeded/python.exe -m pytest -q \
        test_rvc_safe_load_torch.py
    (cwd=tests/, matching quality-gates/run.py g3's own invocation shape)
"""
import importlib.util
import logging
import os

import pytest
import torch

_HERE = os.path.dirname(os.path.abspath(__file__))
_MODULE_FILE = os.path.join(_HERE, "..", "voice", "_safe_load.py")


def _load_module_under_test():
    spec = importlib.util.spec_from_file_location("_misaka_safe_load_torch", _MODULE_FILE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def safe_load(monkeypatch):
    monkeypatch.delenv("MISAKA_PM_RVC_STRICT_LOAD", raising=False)
    return _load_module_under_test()


@pytest.fixture()
def ckpt_path(tmp_path):
    return str(tmp_path / "ckpt.pth")


def test_synthetic_rvc_checkpoint_loads_via_safe_path(safe_load, ckpt_path, caplog, capsys):
    """A plain dict of tensors/lists/strings/ints — the standard RVC checkpoint
    shape (`{"weight": state_dict, "config": [...], "version": ..., ...}`) —
    needs no custom allowlist at all and must succeed on the FIRST
    (weights_only=True) attempt, with no fallback warning."""
    checkpoint = {
        "weight": {
            "enc_p.emb_phone.weight": torch.arange(32, dtype=torch.float32).reshape(4, 8),
            "dec.conv_pre.weight": torch.arange(12, dtype=torch.float32).reshape(2, 2, 3),
        },
        "config": [1, 2, 3, 192, 4],
        "version": "v2",
        "sr": "40k",
        "f0": 1,
        "info": "synthetic test checkpoint",
    }
    torch.save(checkpoint, ckpt_path)
    caplog.set_level(logging.WARNING)

    result = safe_load.load_checkpoint(ckpt_path)

    assert result["version"] == "v2"
    assert result["sr"] == "40k"
    assert result["f0"] == 1
    assert torch.equal(
        result["weight"]["enc_p.emb_phone.weight"],
        checkpoint["weight"]["enc_p.emb_phone.weight"],
    )
    assert not any(rec.levelno >= logging.WARNING for rec in caplog.records)
    assert capsys.readouterr().out == ""


class _DisallowedGlobal(dict):
    """A class NOT in any safe_globals allowlist — forces weights_only=True to
    reject unpickling it, so the fallback path is what has to load this."""


def test_disallowed_global_falls_back_with_warning(safe_load, ckpt_path, caplog, capsys):
    payload = _DisallowedGlobal(weight="unsafe-but-loadable")
    torch.save(payload, ckpt_path)
    caplog.set_level(logging.WARNING)

    result = safe_load.load_checkpoint(ckpt_path)

    assert isinstance(result, _DisallowedGlobal)
    assert result["weight"] == "unsafe-but-loadable"
    assert any(rec.levelno == logging.WARNING for rec in caplog.records)
    assert ckpt_path in caplog.text
    assert ckpt_path in capsys.readouterr().out


def test_strict_mode_raises_instead_of_falling_back(safe_load, ckpt_path, monkeypatch):
    monkeypatch.setenv("MISAKA_PM_RVC_STRICT_LOAD", "1")
    payload = _DisallowedGlobal(weight="unsafe")
    torch.save(payload, ckpt_path)

    with pytest.raises(RuntimeError):
        safe_load.load_checkpoint(ckpt_path)


# ---------------------------------------------------------------------------
# 待回答 #49 review F1 — a corrupt/malformed file must raise directly and
# must NEVER trigger the unsafe (weights_only=False) fallback or print the
# "this may run arbitrary code" warning. The previous implementation decided
# the fallback by catching pickle.UnpicklingError/RuntimeError from a first
# weights_only=True attempt, and torch raises exactly those same exception
# types for a truncated zip / garbage bytes — so a merely damaged download
# used to be treated identically to a genuinely fork-specific model. These
# are real-torch, real-file tests (no mocking) confirming the fix.
# ---------------------------------------------------------------------------


def test_truncated_checkpoint_raises_without_fallback_or_warning(
    safe_load, ckpt_path, caplog, capsys
):
    checkpoint = {"weight": {"a": torch.arange(4, dtype=torch.float32).reshape(2, 2)}, "config": [1], "version": "v2"}
    torch.save(checkpoint, ckpt_path)
    full_bytes = open(ckpt_path, "rb").read()
    with open(ckpt_path, "wb") as f:
        f.write(full_bytes[: len(full_bytes) // 2])
    caplog.set_level(logging.WARNING)

    with pytest.raises(RuntimeError):
        safe_load.load_checkpoint(ckpt_path)

    assert not any(rec.levelno >= logging.WARNING for rec in caplog.records)
    assert capsys.readouterr().out == ""


def test_garbage_bytes_checkpoint_raises_without_fallback_or_warning(
    safe_load, ckpt_path, caplog, capsys
):
    with open(ckpt_path, "wb") as f:
        f.write(b"not a torch checkpoint, just garbage bytes 1234567890")
    caplog.set_level(logging.WARNING)

    with pytest.raises(ValueError):
        safe_load.load_checkpoint(ckpt_path)

    assert not any(rec.levelno >= logging.WARNING for rec in caplog.records)
    assert capsys.readouterr().out == ""
