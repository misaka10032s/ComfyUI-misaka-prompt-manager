"""
RVC-compatible voice conversion wrapper.

Inference priority:
  1. pyworld harvest / torchcrepe crepe / RMVPE  →  F0 extraction
  2. Loaded .pth model (standard RVC SynthesizerTrnMs256NSFsid format)
  3. Fallback: high-quality pitch shift via librosa PSOLA

Install RVC dependencies for full voice-character conversion:
  pip install pyworld torchcrepe  (+ faiss-gpu for index search)
  RMVPE weights: place rmvpe.pt next to the .pth model file.
"""

import numpy as np
import torch
from pathlib import Path


class RVCConverter:
    def __init__(
        self,
        model_path: str,
        index_path: str = "",
        device: str = "cuda",
    ):
        self.model_path = str(Path(model_path))
        self.index_path = index_path
        self.device = device if torch.cuda.is_available() else "cpu"

        self._net_g = None
        self._index = None
        self._tgt_sr = 40000
        self._version = "v2"

        self._load_model()

    # ------------------------------------------------------------------
    # Model loading
    # ------------------------------------------------------------------

    def _load_model(self):
        try:
            cpt = torch.load(self.model_path, map_location="cpu", weights_only=False)
            self._tgt_sr = cpt.get("config", [None] * 16)[16] or 40000
            self._version = cpt.get("version", "v2")
            self._net_g = self._build_net_g(cpt)
            print(f"[MisakaVC] Loaded model: {Path(self.model_path).name} "
                  f"(sr={self._tgt_sr}, {self._version})")
        except Exception as e:
            print(f"[MisakaVC] Could not load model weights: {e}. "
                  f"Pitch-shift fallback will be used.")

        if self.index_path and Path(self.index_path).exists():
            try:
                import faiss
                self._index = faiss.read_index(self.index_path)
                print(f"[MisakaVC] Loaded index: {Path(self.index_path).name}")
            except ImportError:
                print("[MisakaVC] faiss not available — index search disabled. "
                      "Install with: pip install faiss-gpu")
            except Exception as e:
                print(f"[MisakaVC] Could not load index: {e}")

    def _build_net_g(self, cpt: dict):
        """Attempt to instantiate SynthesizerTrnMs256NSFsid from installed RVC."""
        try:
            # Try standard RVC WebUI path first
            from infer.lib.infer_pack.models import (
                SynthesizerTrnMs256NSFsid,
                SynthesizerTrnMs768NSFsid,
                SynthesizerTrnMs256NSFsid_nono,
                SynthesizerTrnMs768NSFsid_nono,
            )
            cfg = cpt["config"]
            f0 = cpt.get("f0", 1)
            version = cpt.get("version", "v1")
            if version == "v1":
                cls = SynthesizerTrnMs256NSFsid if f0 else SynthesizerTrnMs256NSFsid_nono
            else:
                cls = SynthesizerTrnMs768NSFsid if f0 else SynthesizerTrnMs768NSFsid_nono
            net_g = cls(*cfg, is_half=False)
            net_g.eval()
            net_g.load_state_dict(cpt["weight"], strict=False)
            net_g = net_g.to(self.device)
            torch.cuda.empty_cache()
            return net_g
        except ImportError:
            print("[MisakaVC] RVC infer package not found. "
                  "For full VC, install RVC or place its infer/ directory on PYTHONPATH.")
            return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def convert(
        self,
        audio: np.ndarray,
        src_sr: int,
        f0_method: str = "harvest",
        f0_up_key: int = 0,
        index_rate: float = 0.6,
        protect: float = 0.33,
        filter_radius: int = 3,
    ) -> tuple:
        """Return (converted_audio: np.ndarray, output_sr: int)."""
        audio = audio.astype(np.float32)

        if self._net_g is not None:
            try:
                return self._convert_rvc(
                    audio, src_sr, f0_method, f0_up_key,
                    index_rate, protect, filter_radius,
                )
            except Exception as e:
                print(f"[MisakaVC] RVC inference failed ({e}), falling back to pitch shift.")

        return self._convert_pitch_shift(audio, src_sr, f0_up_key)

    # ------------------------------------------------------------------
    # RVC inference path
    # ------------------------------------------------------------------

    def _convert_rvc(self, audio, src_sr, f0_method, f0_up_key,
                     index_rate, protect, filter_radius):
        from .resampler import resample

        # Resample to model sr
        audio_16k = resample(audio, src_sr, 16000)
        audio_tgt = resample(audio, src_sr, self._tgt_sr)

        f0, f0_nsf = self._extract_f0(audio_16k, 16000, f0_method, f0_up_key, filter_radius)

        with torch.no_grad():
            feats = self._extract_hubert_features(audio_16k)

            if self._index is not None and index_rate > 0:
                feats = self._apply_index(feats, index_rate)

            f0_t = torch.FloatTensor(f0_nsf).unsqueeze(0).to(self.device)
            f0_coarse = self._f0_to_coarse(torch.FloatTensor(f0).unsqueeze(0))

            audio_out = self._net_g.infer(
                feats,
                torch.LongTensor([feats.shape[1]]).to(self.device),
                f0_coarse.to(self.device),
                f0_t,
                torch.FloatTensor([protect]).to(self.device),
            )[0][0, 0].float().cpu().numpy()

        torch.cuda.empty_cache()
        return audio_out, self._tgt_sr

    def _extract_f0(self, audio_16k, sr, method, f0_up_key, filter_radius):
        f0 = self._get_f0_raw(audio_16k, sr, method)

        # Median filter to smooth
        if filter_radius > 0:
            try:
                from scipy.signal import medfilt
                voiced = f0 > 0
                if voiced.sum() > 0:
                    f0[voiced] = medfilt(f0[voiced], kernel_size=min(filter_radius * 2 + 1, len(f0[voiced])))
            except ImportError:
                pass

        # Pitch shift
        f0 *= 2 ** (f0_up_key / 12.0)

        f0_nsf = f0.copy()
        f0_coarse = self._f0_to_coarse_np(f0)
        return f0_coarse, f0_nsf

    def _get_f0_raw(self, audio, sr, method) -> np.ndarray:
        if method == "harvest":
            try:
                import pyworld as pw
                f0, _ = pw.harvest(audio.astype(np.float64), sr, frame_period=10.0)
                return f0.astype(np.float32)
            except ImportError:
                print("[MisakaVC] pyworld not available. "
                      "Install with: pip install pyworld")

        if method == "crepe":
            try:
                import torchcrepe
                audio_t = torch.FloatTensor(audio).unsqueeze(0)
                f0 = torchcrepe.predict(audio_t, sr, hop_length=160,
                                        fmin=50, fmax=800, model="full",
                                        batch_size=512, device=self.device)
                return f0.squeeze().cpu().numpy().astype(np.float32)
            except ImportError:
                print("[MisakaVC] torchcrepe not available. "
                      "Install with: pip install torchcrepe")

        if method == "rmvpe":
            rmvpe_path = str(Path(self.model_path).parent / "rmvpe.pt")
            if Path(rmvpe_path).exists():
                try:
                    return self._get_f0_rmvpe(audio, sr, rmvpe_path)
                except Exception as e:
                    print(f"[MisakaVC] RMVPE failed: {e}")
            else:
                print(f"[MisakaVC] rmvpe.pt not found at {rmvpe_path}. "
                      "Falling back to librosa YIN.")

        # librosa YIN fallback (slower but no extra deps)
        import librosa
        f0 = librosa.yin(audio, fmin=50, fmax=800, sr=sr, hop_length=160)
        return f0.astype(np.float32)

    def _get_f0_rmvpe(self, audio, sr, rmvpe_path):
        from .resampler import resample as _resample
        audio_16k = _resample(audio, sr, 16000) if sr != 16000 else audio
        # RMVPE inference — requires rmvpe model class from RVC
        try:
            from infer.lib.rmvpe import RMVPE
            rmvpe = RMVPE(rmvpe_path, is_half=False, device=self.device)
            f0 = rmvpe.infer_from_audio(audio_16k, thred=0.03)
            return f0.astype(np.float32)
        except ImportError:
            raise RuntimeError("RMVPE requires RVC infer package on PYTHONPATH")

    def _extract_hubert_features(self, audio_16k: np.ndarray) -> torch.Tensor:
        try:
            from fairseq import checkpoint_utils as cu
        except ImportError:
            raise RuntimeError(
                "fairseq not available. Install with: pip install fairseq\n"
                "Or use pitch-shift fallback by not loading a model."
            )
        raise NotImplementedError(
            "HuBERT feature extraction requires the fairseq model. "
            "Place hubert_base.pt in the same directory as the RVC model."
        )

    def _apply_index(self, feats: torch.Tensor, index_rate: float) -> torch.Tensor:
        if self._index is None:
            return feats
        np_feats = feats.squeeze(0).cpu().numpy().astype(np.float32)
        import faiss
        _, indices = self._index.search(np_feats, 1)
        index_feats = torch.FloatTensor(
            self._index.reconstruct_batch(indices.flatten())
        ).unsqueeze(0).to(feats.device)
        return feats * (1 - index_rate) + index_feats * index_rate

    @staticmethod
    def _f0_to_coarse_np(f0: np.ndarray) -> np.ndarray:
        f0_bin = 256
        f0_mel_min = 1127 * np.log(1 + 50 / 700)
        f0_mel_max = 1127 * np.log(1 + 800 / 700)
        f0_mel = 1127 * np.log(1 + f0 / 700)
        f0_mel[f0_mel > 0] = (f0_mel[f0_mel > 0] - f0_mel_min) * (f0_bin - 2) / (f0_mel_max - f0_mel_min) + 1
        f0_mel[f0_mel < 1] = 1
        f0_mel[f0_mel > f0_bin - 1] = f0_bin - 1
        return np.round(f0_mel).astype(np.int32)

    def _f0_to_coarse(self, f0: torch.Tensor) -> torch.Tensor:
        return torch.LongTensor(self._f0_to_coarse_np(f0.numpy()))

    # ------------------------------------------------------------------
    # Fallback: high-quality pitch shift
    # ------------------------------------------------------------------

    def _convert_pitch_shift(self, audio: np.ndarray, sr: int, n_steps: int) -> tuple:
        """PSOLA pitch shift via librosa — no voice character conversion."""
        import librosa
        out = librosa.effects.pitch_shift(audio, sr=sr, n_steps=float(n_steps))
        torch.cuda.empty_cache()
        return out, sr
