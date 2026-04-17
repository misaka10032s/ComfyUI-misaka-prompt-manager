import numpy as np


def resample(audio: np.ndarray, src_sr: int, dst_sr: int) -> np.ndarray:
    """High-quality resample using soxr HQ (no aliasing)."""
    if src_sr == dst_sr:
        return audio
    import soxr
    return soxr.resample(audio.astype(np.float32), src_sr, dst_sr, quality="HQ")


def detect_sr(path: str) -> int:
    """Read sample rate without loading the full file."""
    import soundfile as sf
    return sf.info(path).samplerate


def choose_model_sr(input_sr: int, available: list = None) -> int:
    """
    Pick the closest RVC model sample rate that does not exceed input_sr.
    Avoids upsampling artifacts; falls back to the lowest option if all are higher.
    """
    if available is None:
        available = [32000, 40000, 48000]
    candidates = [s for s in sorted(available) if s <= input_sr]
    return candidates[-1] if candidates else min(available)
