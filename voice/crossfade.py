import numpy as np


def concat_with_crossfade(
    segments: list,
    cut_points: list,
    sr: int,
    fade_ms: int = 100,
) -> np.ndarray:
    """
    Stitch RVC-converted segments back together.

    Each segment corresponds to the padded range in cut_points.
    Overlap regions are blended with a linear cross-fade.
    Output is peak-normalised.
    """
    if not segments:
        return np.array([], dtype=np.float32)

    fade_samples = int(fade_ms * sr / 1000)

    # Trim padding from each segment to recover the exact boundary audio
    trimmed = []
    for seg, cp in zip(segments, cut_points):
        seg = np.asarray(seg, dtype=np.float32)
        start_off = cp["start"] - cp["padded_start"]
        end_off = cp["padded_end"] - cp["end"]
        end_idx = len(seg) - end_off if end_off > 0 else len(seg)
        trimmed.append(seg[start_off:end_idx])

    result = trimmed[0].copy()

    for i in range(1, len(trimmed)):
        nxt = trimmed[i]
        f = min(fade_samples, len(result), len(nxt))

        if f > 0:
            t = np.linspace(0.0, 1.0, f, dtype=np.float32)
            # Blend last f samples of result with first f samples of nxt
            result[-f:] = result[-f:] * (1.0 - t) + nxt[:f] * t
            result = np.concatenate([result, nxt[f:]])
        else:
            result = np.concatenate([result, nxt])

    return _peak_normalize(result)


def _peak_normalize(audio: np.ndarray, target: float = 0.95) -> np.ndarray:
    peak = np.max(np.abs(audio))
    if peak > 1e-6:
        return audio * (target / peak)
    return audio
