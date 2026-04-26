"""
RVC voice conversion — no fairseq / no rvc-python.

Dependencies (all numpy 2.x compatible):
  pip install transformers  — HuBERT feature extraction
  pyworld                   — F0 extraction (usually already installed)
  torch / faiss-cpu         — bundled with ComfyUI

HuBERT model is auto-downloaded from HuggingFace on first use.
"""

import sys
import types
import importlib.abc
import importlib.machinery
import numpy as np
import torch
import torch.nn.functional as F
from pathlib import Path

_HUBERT_CACHE: dict = {}

# ---------------------------------------------------------------------------
# Meta-path finder: intercepts ANY import from known RVC fork namespaces
# and returns a fake module so pickle can reconstruct model objects without
# having the original package installed.
# ---------------------------------------------------------------------------

_RVC_ROOTS = frozenset(["ultimate_rvc", "infer", "lib"])


def _make_placeholder_class(name: str):
    """
    Return a flexible stub class for any unknown attribute on a fake module.
    Handles enums, TypedDicts, Pydantic models, etc. from RVC fork packages:
    - Instances are string-like so they survive str() comparisons.
    - __reduce__ lets pickle round-trip them.
    - __getattr__ absorbs any attribute access on the class or instance.
    """
    def _new(cls, value="", *a, **kw):
        obj = str.__new__(cls, str(value))
        obj._value = value
        return obj

    def _reduce(self):
        return (type(self), (str(self),))

    def _getattr(self, attr):
        return None

    @classmethod
    def _cls_getattr(cls, attr):          # class-level attribute access
        return None

    stub = type(name, (str,), {
        "__new__":       _new,
        "__reduce__":    _reduce,
        "__getattr__":   _getattr,
        "__class_getitem__": classmethod(lambda cls, item: cls),
    })
    return stub


class _RVCForkFinder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Handles `import ultimate_rvc.anything` transparently."""

    def find_spec(self, fullname, path, target=None):
        root = fullname.split(".")[0]
        if root in _RVC_ROOTS:
            return importlib.machinery.ModuleSpec(
                fullname, self, is_package=True
            )
        return None

    def create_module(self, spec):
        return None  # use default object

    def exec_module(self, module):
        module.__path__ = []
        module.__package__ = module.__name__.split(".")[0]
        self._populate(module)
        # Any attribute not explicitly set returns a flexible placeholder class.
        # This handles enums/TypedDicts/Pydantic models from the real package.
        module.__getattr__ = _make_placeholder_class

    @staticmethod
    def _populate(module):
        """Add our model classes + common typing stubs to the fake module."""
        try:
            from . import rvc_model
            for name in dir(rvc_model):
                obj = getattr(rvc_model, name)
                if isinstance(obj, type) and not hasattr(module, name):
                    setattr(module, name, obj)
        except Exception:
            pass
        import typing
        for attr in ("Optional", "Union", "List", "Dict", "Tuple", "Any",
                     "Callable", "Type", "Set", "Sequence", "Mapping",
                     "ClassVar", "Final", "Literal", "TypeVar", "Generic",
                     "overload", "cast", "TYPE_CHECKING"):
            if not hasattr(module, attr):
                setattr(module, attr, getattr(typing, attr, object))


_rvc_finder = _RVCForkFinder()


def _install_rvc_finder():
    if not any(isinstance(f, _RVCForkFinder) for f in sys.meta_path):
        sys.meta_path.insert(0, _rvc_finder)
    # Also pre-populate already-registered stubs (from a previous bad run)
    for key in list(sys.modules):
        root = key.split(".")[0]
        if root in _RVC_ROOTS:
            _rvc_finder._populate(sys.modules[key])


# ---------------------------------------------------------------------------
# HuBERT feature extraction (replaces fairseq)
# ---------------------------------------------------------------------------


def _load_hubert(device: str, version: str):
    """
    Both v1 and v2 RVC models were trained against ContentVec — NOT plain HuBERT.
    Using facebook/hubert-base-ls960 here produces features in the right shape
    but the wrong distribution, which is heard as correct-timbre-but-broken-content.

    - v1 (256-dim emb_phone): ContentVec last_hidden_state → final_proj (768→256)
    - v2 (768-dim emb_phone): ContentVec last_hidden_state (768)

    Source model: lengyue233/content-vec-best — a HF port of ContentVec with
    the classifier_proj weights included, used unchanged by Ultimate RVC.
    """
    cache_key = (device, version)
    if cache_key in _HUBERT_CACHE:
        return _HUBERT_CACHE[cache_key]
    try:
        from transformers import HubertModel
        import torch.nn as _nn
    except ImportError:
        raise RuntimeError(
            "[MisakaVC] 'transformers' not installed.\n"
            "  Fix: python_embeded\\python.exe -m pip install transformers"
        )

    class HubertModelWithFinalProj(HubertModel):
        def __init__(self, cfg):
            super().__init__(cfg)
            self.final_proj = _nn.Linear(cfg.hidden_size, cfg.classifier_proj_size)

    model_id = "lengyue233/content-vec-best"
    print(f"[MisakaVC] Loading ContentVec ({model_id}) for {version}…")
    if version == "v1":
        try:
            model = HubertModelWithFinalProj.from_pretrained(model_id)
        except Exception as e:
            print(f"[MisakaVC] final_proj load failed ({e}); using plain HubertModel — "
                  "v1 models may produce mangled audio.")
            model = HubertModel.from_pretrained(model_id)
    else:
        model = HubertModel.from_pretrained(model_id)
    model = model.eval().to(device)
    print(f"[MisakaVC] ContentVec ready (hidden_size={model.config.hidden_size}).")
    _HUBERT_CACHE[cache_key] = model
    return model


def _extract_features(audio_16k: np.ndarray, device: str, version: str) -> torch.Tensor:
    """
    Returns (1, T, C) at 50 fps — caller upsamples 2× before feeding the generator.

    Exactly matches Ultimate RVC's inference path:
        feats = model(wav)["last_hidden_state"]
        if v1: feats = model.final_proj(feats[0]).unsqueeze(0)
    """
    hubert = _load_hubert(device, version)
    wav = torch.from_numpy(audio_16k).float().view(1, -1).to(device)
    with torch.no_grad():
        feats = hubert(wav).last_hidden_state    # (1, T_50fps, hidden_size=768)
        if version == "v1" and hasattr(hubert, "final_proj"):
            feats = hubert.final_proj(feats[0]).unsqueeze(0)  # (1, T, 256)
    return feats


def _upsample2x(feats: torch.Tensor) -> torch.Tensor:
    """Upsample (1, T, C) → (1, 2T, C) with nearest interpolation (RVC convention)."""
    return F.interpolate(feats.transpose(1, 2), scale_factor=2,
                         mode="nearest").transpose(1, 2)


# ---------------------------------------------------------------------------
# F0 extraction via pyworld
# ---------------------------------------------------------------------------

_F0_MIN = 50.0
_F0_MAX = 1100.0
_F0_MEL_MIN = 1127 * np.log(1 + _F0_MIN / 700)
_F0_MEL_MAX = 1127 * np.log(1 + _F0_MAX / 700)

# High-pass filter matching Ultimate RVC (48 Hz, 5th order Butterworth at 16 kHz)
from scipy import signal as _signal
_BH, _AH = _signal.butter(5, 48, btype="high", fs=16000)


def _extract_f0(audio_16k: np.ndarray, p_len: int, f0_up_key: int,
                filter_radius: int) -> tuple:
    """Extract F0 from 16 kHz audio, matching Ultimate RVC's approach."""
    try:
        import pyworld as pw
    except ImportError:
        raise RuntimeError(
            "[MisakaVC] 'pyworld' not installed.\n"
            "  Fix: python_embeded\\python.exe -m pip install pyworld"
        )
    f0, _ = pw.harvest(audio_16k.astype(np.float64), 16000,
                       f0_floor=_F0_MIN, f0_ceil=_F0_MAX, frame_period=10.0)
    if filter_radius > 2:
        from scipy.signal import medfilt
        k = filter_radius if filter_radius % 2 == 1 else filter_radius + 1
        f0 = medfilt(f0, k)
    f0 = f0[:p_len]
    if f0_up_key != 0:
        f0 *= 2 ** (f0_up_key / 12.0)
        f0 = np.clip(f0, _F0_MIN, _F0_MAX)

    f0_bak = f0.copy()
    f0_mel = 1127 * np.log(1 + f0 / 700)
    f0_mel[f0_mel > 0] = (f0_mel[f0_mel > 0] - _F0_MEL_MIN) * 254 / (
        _F0_MEL_MAX - _F0_MEL_MIN) + 1
    f0_mel[f0_mel <= 1] = 1
    f0_mel[f0_mel > 255] = 255
    f0_coarse = np.rint(f0_mel).astype(np.int32)
    return f0_coarse, f0_bak


# ---------------------------------------------------------------------------
# Volume-envelope matching (Ultimate RVC AudioProcessor.change_rms)
# ---------------------------------------------------------------------------

def _change_rms(src: np.ndarray, src_sr: int, tgt: np.ndarray, tgt_sr: int,
                rate: float) -> np.ndarray:
    """
    Blend target audio's RMS envelope toward source audio's RMS envelope.
    rate=1.0 → keep target as-is; rate=0.0 → fully match source.
    """
    import librosa
    rms_src = librosa.feature.rms(y=src, frame_length=src_sr // 2 * 2,
                                  hop_length=src_sr // 2)
    rms_tgt = librosa.feature.rms(y=tgt, frame_length=tgt_sr // 2 * 2,
                                  hop_length=tgt_sr // 2)
    rms_src_t = F.interpolate(torch.from_numpy(rms_src).float().unsqueeze(0),
                              size=tgt.shape[0], mode="linear").squeeze()
    rms_tgt_t = F.interpolate(torch.from_numpy(rms_tgt).float().unsqueeze(0),
                              size=tgt.shape[0], mode="linear").squeeze()
    rms_tgt_t = torch.maximum(rms_tgt_t, torch.zeros_like(rms_tgt_t) + 1e-6)
    scale = (torch.pow(rms_src_t, 1.0 - rate)
             * torch.pow(rms_tgt_t, rate - 1.0)).numpy()
    return (tgt * scale).astype(np.float32)


# ---------------------------------------------------------------------------
# Build our model from config + state dict
# ---------------------------------------------------------------------------

def _detect_arch_params(weights, hidden_channels):
    """Infer window_size and flow WN n_layers from actual weight shapes."""
    window_size = 4
    flow_wn_layers = 4
    for key, val in weights.items():
        if "enc_p.encoder.attn_layers.0.emb_rel_k" in key:
            window_size = (val.shape[1] - 1) // 2
        if "flow.flows.0.enc.cond_layer.bias" in key and hidden_channels > 0:
            # shape = 2 * hidden_channels * n_layers
            flow_wn_layers = max(1, val.shape[0] // (2 * hidden_channels))
    return window_size, flow_wn_layers


def _build_and_load(cfg, version, weights):
    from .rvc_model import SynthesizerTrnMs256NSFsid, SynthesizerTrnMs768NSFsid
    Cls = SynthesizerTrnMs256NSFsid if version == "v1" else SynthesizerTrnMs768NSFsid

    hidden_channels = cfg[3] if len(cfg) > 3 else 192
    clean = {k.replace("module.", ""): v for k, v in weights.items()}
    window_size, flow_wn_layers = _detect_arch_params(clean, hidden_channels)
    print(f"[MisakaVC] Detected: window_size={window_size}, flow_wn_layers={flow_wn_layers}")

    try:
        net_g = Cls(*cfg, is_half=False,
                    window_size=window_size, flow_wn_layers=flow_wn_layers)
    except Exception as e:
        raise RuntimeError(
            f"[MisakaVC] Cannot build model from config {cfg}: {e}"
        ) from e

    # Some checkpoints are partially de-normed: most layers have weight_g/weight_v
    # but a few (e.g. conv_pre, conv_post) only have plain weight.
    # For those, decompose plain weight → (weight_g, weight_v) so the model's
    # weight_norm structure can absorb them correctly.
    model_keys = set(net_g.state_dict().keys())
    patched = {}
    decomposed = []
    for key, val in clean.items():
        g_key = key[:-7] + ".weight_g"   # only valid when key ends with ".weight"
        v_key = key[:-7] + ".weight_v"
        if (key.endswith(".weight")
                and g_key not in clean          # checkpoint doesn't have weight_g
                and g_key in model_keys):       # but our model does (weight_norm layer)
            # Decompose: weight_v = weight, weight_g = per-filter L2 norm
            norm_dims = list(range(1, val.ndim))
            g = val.norm(dim=norm_dims, keepdim=True)
            patched[g_key] = g
            patched[v_key] = val
            decomposed.append(key)
        else:
            patched[key] = val
    if decomposed:
        print(f"[MisakaVC] Decomposed {len(decomposed)} plain weight(s) → weight_norm: {decomposed}")
    clean = patched

    missing, unexpected = net_g.load_state_dict(clean, strict=False)
    if missing:
        print(f"[MisakaVC] Missing weight keys ({len(missing)} total, first 5): {missing[:5]}")
    if unexpected:
        print(f"[MisakaVC] Unexpected weight keys ({len(unexpected)} total, first 5): {unexpected[:5]}")
    return net_g


def _state_dict_from_object(obj) -> dict:
    """Walk an arbitrary object tree and collect all tensor leaves."""
    result = {}

    def _walk(o, prefix):
        d = getattr(o, "__dict__", {})
        for key in ("_parameters", "_buffers"):
            for k, v in d.get(key, {}).items():
                if v is not None:
                    result[f"{prefix}{k}"] = v
        for k, v in d.get("_modules", {}).items():
            if v is not None:
                _walk(v, f"{prefix}{k}.")

    _walk(obj, "")
    return result


# ---------------------------------------------------------------------------
# Main converter
# ---------------------------------------------------------------------------

class RVCConverter:
    def __init__(self, model_path: str, index_path: str = "", device: str = "cuda"):
        self.model_path = str(Path(model_path))
        self.index_path = index_path or ""
        self.device = device if torch.cuda.is_available() else "cpu"
        self._net_g = None
        self._version = "v1"
        self._out_sr = 40000
        self._use_f0 = True
        self._index = None
        self._default_f0_method = "harvest"
        self._load_model()

    def _load_model(self):
        _install_rvc_finder()

        try:
            cpt = torch.load(self.model_path, map_location="cpu", weights_only=False)
        except Exception as e:
            raise RuntimeError(f"[MisakaVC] Cannot open model file: {e}") from e

        # ── standard RVC dict: {"weight": ..., "config": ..., "version": ...}
        if isinstance(cpt, dict) and "weight" in cpt:
            cfg = cpt.get("config", [])
            raw_version = cpt.get("version", None)
            # Also try to infer version from weight shapes if not stored
            if raw_version is None:
                phone_w = cpt["weight"].get("enc_p.emb_phone.weight")
                if phone_w is not None:
                    raw_version = "v1" if phone_w.shape[1] <= 256 else "v2"
                else:
                    raw_version = "v1"
            self._version = raw_version
            self._use_f0 = bool(cpt.get("f0", 1))
            sr_str = str(cpt.get("sr", "40k"))
            self._out_sr = 48000 if "48" in sr_str else 40000
            print(f"[MisakaVC] Dict model: version={self._version}, sr={self._out_sr}, "
                  f"cfg={cfg}")
            net_g = _build_and_load(cfg, self._version, cpt["weight"])

        # ── full model object (torch.save(model, path))
        elif hasattr(cpt, "infer") or hasattr(cpt, "enc_p"):
            net_g = cpt
            try:
                in_f = net_g.enc_p.emb_phone.in_features
                self._version = "v1" if in_f <= 256 else "v2"
                print(f"[MisakaVC] Full-object model: emb_phone.in_features={in_f} → version={self._version}")
            except Exception as e:
                print(f"[MisakaVC] Could not read emb_phone.in_features: {e} — defaulting to v2")
                self._version = "v2"
            try:
                ups = net_g.dec.f0_upsamp.scale_factor
                self._out_sr = 48000 if int(ups) == 960 else 40000
            except Exception:
                pass

        # ── object was reconstructed but wrong class (proxy/unknown)
        elif not isinstance(cpt, dict):
            print("[MisakaVC] Model loaded as unknown object — extracting state dict…")
            weights = _state_dict_from_object(cpt)
            if not weights:
                raise RuntimeError(
                    "[MisakaVC] Could not extract weights from model file.\n"
                    "  This model was saved by a fork of RVC that we can't reconstruct.\n"
                    "  Please re-export it from the original tool as a standard RVC checkpoint."
                )
            # Guess version from weight key dims
            phone_w = weights.get("enc_p.emb_phone.weight")
            if phone_w is not None:
                self._version = "v1" if phone_w.shape[1] <= 256 else "v2"
            # We need config — try to infer from weight shapes
            raise RuntimeError(
                "[MisakaVC] Model is in a non-standard format without embedded config.\n"
                "  Cannot determine architecture automatically.\n"
                "  Please re-export from the training tool as a standard RVC checkpoint."
            )

        else:
            raise RuntimeError(
                f"[MisakaVC] Unrecognised model format: {type(cpt)}\n"
                "  Expected a dict with 'weight'/'config' keys or a full model object."
            )

        # Force float32 — checkpoint may carry float16 tensors after load_state_dict
        self._net_g = net_g.float().eval().to(self.device)
        print(f"[MisakaVC] Loaded: {Path(self.model_path).name} "
              f"(version={self._version}, sr={self._out_sr}, f0={self._use_f0})")

        self._big_npy = None
        if self.index_path and Path(self.index_path).is_file():
            try:
                import faiss
                self._index = faiss.read_index(self.index_path)
                self._big_npy = self._index.reconstruct_n(0, self._index.ntotal)
                print(f"[MisakaVC] Index: {Path(self.index_path).name} "
                      f"({self._index.ntotal} vectors)")
            except Exception as e:
                print(f"[MisakaVC] Index load failed: {e}")

    # ── Per-chunk voice conversion (mirrors Ultimate RVC `voice_conversion`) ──
    def _vc_chunk(self, audio0: np.ndarray, pitch, pitchf, sid,
                  index_rate: float, protect: float) -> np.ndarray:
        """
        audio0: 1-D float32 16 kHz chunk (padded on both sides with t_pad)
        pitch / pitchf: sliced frame-rate tensors aligned to this chunk, or None
        Returns 1-D float32 output at self._out_sr.
        """
        with torch.no_grad():
            # HuBERT features at 50 fps
            feats = _extract_features(audio0, self.device, self._version)
            feats0 = feats.clone() if pitch is not None else None

            # FAISS blend at 50 fps (Ultimate RVC applies index here, not after 2x)
            if (self._index is not None and self._big_npy is not None
                    and index_rate > 0):
                npy = feats[0].cpu().numpy()
                try:
                    score, ix = self._index.search(npy.astype(np.float32), k=8)
                    weight = np.square(1.0 / np.maximum(score, 1e-8))
                    weight /= weight.sum(axis=1, keepdims=True)
                    blended = np.sum(self._big_npy[ix] *
                                     np.expand_dims(weight, axis=2), axis=1)
                    feats = (torch.from_numpy(blended).unsqueeze(0).to(
                                 self.device, dtype=feats.dtype) * index_rate
                             + feats * (1.0 - index_rate))
                except Exception as e:
                    print(f"[MisakaVC] FAISS search failed, skipping index: {e}")

            # 2x upsample 50 → 100 fps
            feats = _upsample2x(feats)
            p_len = min(audio0.shape[0] // 160, feats.shape[1])

            if pitch is not None:
                feats0 = _upsample2x(feats0)
                pitch  = pitch[:, :p_len]
                pitchf = pitchf[:, :p_len]
                feats  = feats[:, :p_len, :]
                feats0 = feats0[:, :p_len, :]
                if protect < 0.5:
                    pitchff = pitchf.clone()
                    pitchff[pitchf > 0] = 1.0
                    pitchff[pitchf < 1] = protect
                    feats = feats * pitchff.unsqueeze(-1) + feats0 * (
                        1.0 - pitchff.unsqueeze(-1))
                    feats = feats.to(feats0.dtype)
            else:
                feats = feats[:, :p_len, :]

            p_len_t = torch.tensor([p_len], device=self.device).long()
            audio_out, _ = self._net_g.infer(
                feats.float(), p_len_t,
                pitch, pitchf.float() if pitchf is not None else None, sid)
        result = audio_out[0, 0].data.cpu().float().numpy()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        return result

    def convert(self, audio: np.ndarray, src_sr: int,
                f0_method: str = "harvest", f0_up_key: int = 0,
                index_rate: float = 0.5, protect: float = 0.33,
                rms_mix_rate: float = 0.25) -> tuple:
        """
        Mirror of Ultimate RVC's Pipeline.pipeline() — the important bits:
          • HP filter on ALL audio (not just F0)
          • 1-second reflection pad (x_pad=1)
          • silent-point chunking for audio > ~41 s (x_max=41)
          • F0 extracted once on the whole padded clip; HuBERT features re-extracted
            per chunk with overlap, stripped at the output sample rate.
        """
        import soxr

        # Ultimate RVC default config (x_pad=1, x_query=6, x_center=38, x_max=41)
        sample_rate = 16000
        window = 160
        x_pad, x_query, x_center, x_max = 1, 6, 38, 41
        t_pad       = sample_rate * x_pad          # 16000
        t_pad_tgt   = self._out_sr * x_pad
        t_pad2      = t_pad * 2
        t_query     = sample_rate * x_query        # 96000
        t_center    = sample_rate * x_center       # 608000
        t_max       = sample_rate * x_max          # 656000

        # ── 1. Resample to 16 kHz ──────────────────────────────────────────
        audio = soxr.resample(audio.astype(np.float32), src_sr, sample_rate)

        # ── 2. Peak normalise (matches Ultimate RVC's load_audio_infer) ───
        audio_max_abs = float(np.abs(audio).max()) / 0.95
        if audio_max_abs > 1.0:
            audio = audio / audio_max_abs

        # ── 3. HP filter applied to ALL downstream processing ─────────────
        audio = _signal.filtfilt(_BH, _AH, audio).astype(np.float32)

        # ── 4. Find silent split points if audio > t_max ──────────────────
        opt_ts = []
        audio_sp = np.pad(audio, (window // 2, window // 2), mode="reflect")
        if audio_sp.shape[0] > t_max:
            audio_sum = np.zeros_like(audio)
            for i in range(window):
                audio_sum = audio_sum + audio_sp[i : i - window]
            for t in range(t_center, audio.shape[0], t_center):
                seg = np.abs(audio_sum[t - t_query : t + t_query])
                if len(seg) == 0:
                    continue
                opt_ts.append(t - t_query + int(np.argmin(seg)))
            print(f"[MisakaVC] long audio ({audio.shape[0]/sample_rate:.1f}s) → "
                  f"{len(opt_ts)} split point(s)")

        # ── 5. Big reflection pad for actual processing ───────────────────
        audio_pad = np.pad(audio, (t_pad, t_pad), mode="reflect")
        p_len = audio_pad.shape[0] // window
        sid = torch.LongTensor([0]).to(self.device)

        # ── 6. F0 once on the whole padded clip ───────────────────────────
        if self._use_f0:
            f0_coarse, f0_bak = _extract_f0(audio_pad, p_len, f0_up_key,
                                            filter_radius=3)
            f0_coarse = f0_coarse[:p_len]
            f0_bak    = f0_bak[:p_len]
            pitch  = torch.from_numpy(f0_coarse).unsqueeze(0).long().to(self.device)
            pitchf = torch.from_numpy(f0_bak.astype(np.float32)
                                      ).unsqueeze(0).to(self.device)
            print(f"[MisakaVC] p_len={p_len}, "
                  f"f0_voiced={float((f0_bak>0).mean()):.1%}")
        else:
            pitch = pitchf = None

        # ── 7. Per-chunk conversion with t_pad_tgt overlap trim ───────────
        audio_opt = []
        s = 0
        t = None
        for t in opt_ts:
            t = (t // window) * window
            chunk = audio_pad[s : t + t_pad2 + window]
            cp = pitch[:, s // window : (t + t_pad2) // window] if pitch is not None else None
            cpf = pitchf[:, s // window : (t + t_pad2) // window] if pitchf is not None else None
            out = self._vc_chunk(chunk, cp, cpf, sid, index_rate, protect)
            audio_opt.append(out[t_pad_tgt : -t_pad_tgt])
            s = t

        # final chunk (everything after last split, or the whole clip if no splits)
        final_chunk = audio_pad[t:] if t is not None else audio_pad
        cp = (pitch[:, t // window:] if (pitch is not None and t is not None)
              else pitch)
        cpf = (pitchf[:, t // window:] if (pitchf is not None and t is not None)
               else pitchf)
        out = self._vc_chunk(final_chunk, cp, cpf, sid, index_rate, protect)
        audio_opt.append(out[t_pad_tgt : -t_pad_tgt])

        result = np.concatenate(audio_opt).astype(np.float32)

        # ── 8. Volume envelope (Ultimate RVC's change_rms) ────────────────
        #   rate=1  → keep converted RMS (no change)
        #   rate=0  → fully match source RMS
        if rms_mix_rate < 1.0 - 1e-4:
            result = _change_rms(audio, sample_rate, result,
                                 self._out_sr, rms_mix_rate)

        # ── 9. Peak normalise output ──────────────────────────────────────
        audio_max_out = float(np.abs(result).max()) / 0.99
        if audio_max_out > 1.0:
            result = result / audio_max_out

        print(f"[MisakaVC] output samples={len(result)} "
              f"({len(result)/self._out_sr:.2f}s @ {self._out_sr} Hz), "
              f"rms={float(np.sqrt((result**2).mean())):.4f}")
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        return result, self._out_sr
