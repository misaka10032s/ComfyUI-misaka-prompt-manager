"""
Safe-then-fallback loader for torch pickle checkpoint files (RVC `.pth` models).

Owner ruling (待回答 #49, 2026-09-07, verbatim):
    「修：先安全載入（weights_only=True），失敗才退回舊方式並明確警告」
    「用站主現有 RVC 模型驗證仍可載」

`torch.load(..., weights_only=False)` unpickles arbitrary Python objects — a
malicious `.pth` model file can execute arbitrary code on load. This module
decides the fallback STATICALLY, without ever unpickling an untrusted file to
make that decision: `torch.serialization.get_unsafe_globals_in_checkpoint(path)`
(torch >= 2.4) statically disassembles the checkpoint's pickle stream and
reports exactly which GLOBALs it references that are not already allowlisted
— it never reconstructs any object, so running it carries none of the risk
`weights_only=False` does.

Decision flow (rewritten 2026-09-07, 待回答 #49 review F1 — the previous
version decided the fallback by CATCHING `pickle.UnpicklingError`/
`RuntimeError` raised from a first `weights_only=True` attempt, which also
caught plain file corruption and fired the "this may run arbitrary code"
warning on a merely truncated or garbage file, contradicting this module's
own contract):
  1. Run the static scan first, outside any exception handling that would
     redirect it toward the fallback path. If the file is not a valid torch
     checkpoint at all — truncated zip, garbage bytes, missing file, a
     torchscript archive — the scan itself raises, and that exception
     propagates UNCHANGED. This is an ordinary I/O/format failure, not a
     pickle-trust decision, so it never triggers the unsafe fallback and
     never prints the RCE warning.
  2. If the scan reports NO unsafe globals, the checkpoint needs nothing
     outside torch's own safe defaults plus the caller's `safe_globals`
     allowlist: load with `weights_only=True`. Any exception from this load
     (e.g. a class dynamically pushed onto the unpickle stack, which the
     static scan's own docs say it cannot see) also propagates unchanged —
     it is not a pickle-trust problem this module's fallback logic exists
     to paper over.
  3. If the scan reports unsafe globals, the checkpoint genuinely needs
     something outside the allowlist:
       - strict mode (`MISAKA_PM_RVC_STRICT_LOAD`) -> raise, naming the file
         AND the unsafe globals; the unsafe path is never attempted.
       - default mode -> log + print an explicit WARNING (zh-TW, naming the
         file AND the unsafe globals) and load with `weights_only=False`
         (the old, unrestricted behaviour).
  4. Fallback of last resort, used ONLY if
     `torch.serialization.get_unsafe_globals_in_checkpoint` does not exist
     (torch < 2.4, the API's introduction version): the previous
     exception-based heuristic — attempt `weights_only=True` and treat
     `pickle.UnpicklingError`/`RuntimeError` as "needs the unsafe path".
     This reintroduces the file-corruption false positive the scan-based
     flow above exists to avoid, but only on an old torch this repo is not
     known to run against (measured 2026-09-07: both this machine's gate
     interpreter and the ComfyUI embedded interpreter carry torch
     2.11.0+cu128, well past the 2.4 cutoff).

Kept import-light ON PURPOSE: this module does NOT `import torch` at module
scope, so it stays importable (and unit-testable) under an interpreter that
has no torch installed at all. `torch` is imported lazily inside
`load_checkpoint()`; tests inject a fake module via `sys.modules["torch"]`
before calling it. (This plugin's own quality-gate interpreter, `py -3.11`,
happens to have torch installed on THIS machine as of 2026-09-07 — the
import-light design is for portability to interpreters that may NOT have
torch, not a claim about any specific machine's install state; see 待回答
#49 review F4.)
"""
import logging
import os
import pickle

logger = logging.getLogger(__name__)

# Operator opt-in: disable the unsafe fallback entirely (raise instead).
# Default OFF, per the ruling above — safe-first-then-fallback is the default
# behaviour; strict mode is for operators who never want the unsafe path used.
STRICT_ENV_VAR = "MISAKA_PM_RVC_STRICT_LOAD"

# Accepted truthy spellings for STRICT_ENV_VAR (case-insensitive, surrounding
# whitespace ignored). Anything else — including unset — is OFF. (待回答 #49
# review F7: the previous version accepted only the exact string "1".)
_STRICT_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


def strict_mode_enabled() -> bool:
    """True when the operator has set MISAKA_PM_RVC_STRICT_LOAD to a truthy
    value: `1`, `true`, `yes`, or `on` (case-insensitive). Any other value,
    including unset, is OFF — the default safe-first-then-fallback behaviour
    stays enabled."""
    return os.environ.get(STRICT_ENV_VAR, "").strip().lower() in _STRICT_TRUE_VALUES


def _format_unsafe_globals(unsafe_globals) -> str:
    return ", ".join(sorted(unsafe_globals)) if unsafe_globals else "(none)"


def load_checkpoint(path, safe_globals=None):
    """
    Load `path` via torch.load, deciding the safe-vs-fallback path by
    STATICALLY scanning the checkpoint first — see the module docstring for
    the full decision flow. Never unpickles the file to make that decision.

    Args:
      path: filesystem path to the checkpoint (.pth) file.
      safe_globals: optional iterable of classes (or `(callable, "dotted.path")`
        tuples — see `torch.serialization.safe_globals`) to allowlist for the
        safe path. Pass ONLY entries whose reconstruction is known-harmless
        (plain data holders, this repo's own nn.Module subclasses, or a
        reviewed inert placeholder bound to one specific fork-package global —
        see `voice/rvc_wrapper.py:_rvc_safe_globals`). None/empty means no
        extra allowlist beyond torch's own built-in safe defaults (tensors,
        OrderedDict, dict/list/tuple, numpy scalars, primitives).

    Raises:
      Whatever the static scan or the chosen `torch.load` call raises for a
      missing/corrupt/malformed file — never swallowed, never redirected to
      the unsafe fallback (see module docstring step 1/2).
      RuntimeError if the checkpoint needs a global outside `safe_globals`
      and strict mode is enabled (step 3).
    """
    import torch  # deferred — see module docstring

    globals_list = list(safe_globals) if safe_globals else []
    static_scan = getattr(torch.serialization, "get_unsafe_globals_in_checkpoint", None)

    if static_scan is None:
        # Fallback of last resort — torch too old to have the static scan API
        # (added in torch 2.4). See module docstring step 4.
        return _load_via_exception_heuristic(torch, path, globals_list)

    # Step 1: static, non-unpickling scan. Any exception here (missing file,
    # truncated/garbage archive, torchscript zip, ...) propagates unchanged —
    # it is not a pickle-trust decision.
    if globals_list:
        with torch.serialization.safe_globals(globals_list):
            unsafe_globals = static_scan(path)
    else:
        unsafe_globals = static_scan(path)

    if not unsafe_globals:
        # Step 2: nothing outside the allowlist — safe path only. Any
        # exception from the load itself also propagates unchanged.
        if globals_list:
            with torch.serialization.safe_globals(globals_list):
                result = torch.load(path, map_location="cpu", weights_only=True)
        else:
            result = torch.load(path, map_location="cpu", weights_only=True)
        logger.info("[MisakaVC] weights_only=True 安全載入成功：%s", path)
        return result

    # Step 3: the checkpoint genuinely needs globals outside the allowlist.
    if strict_mode_enabled():
        raise RuntimeError(
            f"[MisakaVC] 靜態掃描發現未被允許的全域物件（{_format_unsafe_globals(unsafe_globals)}），"
            f"且環境變數 {STRICT_ENV_VAR}=1 已停用退回機制，拒絕載入此檔案：{path}"
        )
    message = (
        f"[MisakaVC][WARNING] 模型安全載入失敗（{path} 內含未被允許的全域物件："
        f"{_format_unsafe_globals(unsafe_globals)}），退回舊式 pickle 載入方式"
        f"（weights_only=False，此模式會執行檔案內任意程式碼）。請務必確認你信任"
        f"此模型檔案的來源，再繼續使用。"
    )
    logger.warning(message)
    print(message)
    return torch.load(path, map_location="cpu", weights_only=False)


def _load_via_exception_heuristic(torch, path, globals_list):
    """Fallback of last resort for torch < 2.4 (no
    `get_unsafe_globals_in_checkpoint`). Decides the fallback by CATCHING the
    weights_only unpickler's rejection instead of scanning first — this also
    catches plain file corruption (a truncated/garbage file raises the same
    exception types a disallowed-global rejection does), which is the exact
    false positive the scan-based flow in `load_checkpoint()` exists to
    avoid. Kept only so this module still degrades gracefully on an old
    torch; not exercised by real torch on this repo's supported interpreters
    (both measured at 2.11.0+cu128, see module docstring step 4)."""
    try:
        if globals_list:
            with torch.serialization.safe_globals(globals_list):
                result = torch.load(path, map_location="cpu", weights_only=True)
        else:
            result = torch.load(path, map_location="cpu", weights_only=True)
        logger.info("[MisakaVC] weights_only=True 安全載入成功：%s", path)
        return result
    except (pickle.UnpicklingError, RuntimeError) as e:
        if strict_mode_enabled():
            raise RuntimeError(
                f"[MisakaVC] weights_only=True 安全載入失敗，且環境變數 "
                f"{STRICT_ENV_VAR}=1 已停用退回機制，拒絕載入此檔案：{path}\n"
                f"原始錯誤：{e}"
            ) from e
        message = (
            f"[MisakaVC][WARNING] 模型安全載入失敗（weights_only=True 於 "
            f"{path} 遭拒），退回舊式 pickle 載入方式（weights_only=False，"
            f"此模式會執行檔案內任意程式碼）。請務必確認你信任此模型檔案的來源，"
            f"再繼續使用。原始錯誤：{e}"
        )
        logger.warning(message)
        print(message)
        return torch.load(path, map_location="cpu", weights_only=False)
