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

_FEATURE_DIM_CACHE: dict = {}   # cache model_id → output hidden_size

def _load_hubert(device: str, version: str):
    """
    v1 models (256-dim emb_phone): use ContentVec — lengyue233/content-vec-best
    v2 models (768-dim emb_phone): use HuBERT base — facebook/hubert-base-ls960
    Returns (processor, model, layer, expected_dim)
    """
    cache_key = (device, version)
    if cache_key in _HUBERT_CACHE:
        return _HUBERT_CACHE[cache_key]
    try:
        from transformers import HubertModel, Wav2Vec2FeatureExtractor
    except ImportError:
        raise RuntimeError(
            "[MisakaVC] 'transformers' not installed.\n"
            "  Fix: python_embeded\\python.exe -m pip install transformers"
        )
    if version == "v1":
        model_id = "lengyue233/content-vec-best"
        layer = 9
    else:
        model_id = "facebook/hubert-base-ls960"
        layer = 12
    print(f"[MisakaVC] Loading feature extractor ({model_id})…")
    processor = Wav2Vec2FeatureExtractor.from_pretrained(model_id)
    model = HubertModel.from_pretrained(model_id).eval().to(device)
    hidden_size = model.config.hidden_size
    print(f"[MisakaVC] Feature extractor ready (hidden_size={hidden_size}, layer={layer}).")
    _HUBERT_CACHE[cache_key] = (processor, model, layer, hidden_size)
    return processor, model, layer, hidden_size


def _extract_features(audio_16k: np.ndarray, device: str, version: str) -> torch.Tensor:
    """Returns (1, T*2, C) — C matches what the loaded feature extractor outputs."""
    processor, hubert, layer, _ = _load_hubert(device, version)
    inputs = processor(audio_16k, sampling_rate=16000, return_tensors="pt", padding=True)
    wav = inputs["input_values"].to(device)
    with torch.no_grad():
        out = hubert(wav, output_hidden_states=True)
        feats = out.hidden_states[layer]   # (1, T, hidden_size)
    # RVC convention: upsample T×2
    feats = F.interpolate(feats.transpose(1, 2), scale_factor=2,
                          mode="nearest").transpose(1, 2)
    return feats


# ---------------------------------------------------------------------------
# F0 extraction via pyworld
# ---------------------------------------------------------------------------

def _extract_f0(audio: np.ndarray, sr: int, f0_up_key: int,
                filter_radius: int) -> tuple:
    try:
        import pyworld as pw
    except ImportError:
        raise RuntimeError(
            "[MisakaVC] 'pyworld' not installed.\n"
            "  Fix: python_embeded\\python.exe -m pip install pyworld"
        )
    f0_min, f0_max = 50.0, 1100.0
    f0, _ = pw.harvest(audio.astype(np.float64), sr,
                       f0_floor=f0_min, f0_ceil=f0_max, frame_period=10.0)
    if filter_radius > 2:
        from scipy.signal import medfilt
        k = filter_radius if filter_radius % 2 == 1 else filter_radius + 1
        f0 = medfilt(f0, k)
    if f0_up_key != 0:
        f0 = np.clip(f0 * (2 ** (f0_up_key / 12.0)), f0_min, f0_max)

    f0_bak = f0.copy()
    mel_min = 1127 * np.log(1 + f0_min / 700)
    mel_max = 1127 * np.log(1 + f0_max / 700)
    mel = 1127 * np.log(1 + f0 / 700)
    mel[mel > 0] = (mel[mel > 0] - mel_min) * 254 / (mel_max - mel_min) + 1
    f0_coarse = np.clip(np.round(mel), 1, 255).astype(np.int32)
    return f0_coarse, f0_bak


# ---------------------------------------------------------------------------
# Optional FAISS index refinement
# ---------------------------------------------------------------------------

def _apply_index(feats: np.ndarray, index, index_rate: float) -> np.ndarray:
    if index is None or index_rate == 0:
        return feats
    try:
        import faiss  # noqa
        score, ix = index.search(feats.astype(np.float32), k=8)
        weight = np.square(1.0 / (score + 1e-6))
        weight /= weight.sum(axis=1, keepdims=True)
        vecs = np.stack([index.reconstruct(int(r)) for r in ix.ravel()])
        vecs = vecs.reshape(*ix.shape, feats.shape[-1])
        return feats * (1 - index_rate) + (vecs * weight[..., np.newaxis]).sum(1) * index_rate
    except Exception:
        return feats


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

    missing, unexpected = net_g.load_state_dict(clean, strict=False)
    if missing:
        print(f"[MisakaVC] Missing weight keys (first 5): {missing[:5]}")
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

        self._net_g = net_g.eval().to(self.device)
        print(f"[MisakaVC] Loaded: {Path(self.model_path).name} "
              f"(version={self._version}, sr={self._out_sr}, f0={self._use_f0})")

        if self.index_path and Path(self.index_path).is_file():
            try:
                import faiss
                self._index = faiss.read_index(self.index_path)
                print(f"[MisakaVC] Index: {Path(self.index_path).name}")
            except Exception as e:
                print(f"[MisakaVC] Index load failed: {e}")

    def convert(self, audio: np.ndarray, src_sr: int,
                f0_method: str = "harvest", f0_up_key: int = 0,
                index_rate: float = 0.6, protect: float = 0.33,
                filter_radius: int = 3) -> tuple:
        import soxr

        audio_16k = soxr.resample(audio.astype(np.float32), src_sr, 16000)
        audio_model = soxr.resample(audio.astype(np.float32), src_sr, self._out_sr)

        feats = _extract_features(audio_16k, self.device, self._version)
        feats_np = _apply_index(feats.squeeze(0).cpu().float().numpy(),
                                self._index, index_rate)
        feats = torch.from_numpy(feats_np).unsqueeze(0).to(self.device)
        T = feats.shape[1]

        if self._use_f0:
            f0_coarse, f0_bak = _extract_f0(audio_model, self._out_sr,
                                              f0_up_key, filter_radius)
        else:
            f0_coarse = np.zeros(T, dtype=np.int32)
            f0_bak = np.zeros(T, dtype=np.float32)

        if f0_coarse.shape[0] < T:
            f0_coarse = np.pad(f0_coarse, (0, T - f0_coarse.shape[0]))
            f0_bak = np.pad(f0_bak, (0, T - f0_bak.shape[0]))
        else:
            f0_coarse, f0_bak = f0_coarse[:T], f0_bak[:T]

        pitch = torch.from_numpy(f0_coarse).unsqueeze(0).long().to(self.device)
        pitchf = torch.from_numpy(f0_bak.astype(np.float32)).unsqueeze(0).to(self.device)
        phone_len = torch.LongTensor([T]).to(self.device)
        sid = torch.LongTensor([0]).to(self.device)

        with torch.no_grad():
            audio_out, _ = self._net_g.infer(feats, phone_len, pitch, pitchf, sid)

        result = audio_out[0, 0].cpu().float().numpy()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        return result, self._out_sr
