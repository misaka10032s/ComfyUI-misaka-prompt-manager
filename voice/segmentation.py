import numpy as np


def find_cut_points(
    audio: np.ndarray,
    sr: int,
    min_silence_ms: int = 300,
    silence_threshold_db: float = -40.0,
    max_segment_sec: float = 15.0,
    overlap_ms: int = 150,
) -> list:
    """
    Find silence-based cut points in audio.

    Returns list of dicts with start/end (actual cut) and
    padded_start/padded_end (with overlap, for RVC input).
    All values are sample indices.
    """
    import librosa

    total_samples = len(audio)
    overlap_samples = int(overlap_ms * sr / 1000)
    min_silence_samples = int(min_silence_ms * sr / 1000)
    max_segment_samples = int(max_segment_sec * sr)

    # librosa.effects.split returns non-silent intervals
    # top_db is relative to peak; we convert our absolute dB threshold
    # by using a fixed ref (1.0), so top_db = -silence_threshold_db
    non_silent = librosa.effects.split(
        audio,
        top_db=-silence_threshold_db,
        frame_length=2048,
        hop_length=512,
    )

    if len(non_silent) == 0:
        return [_make_segment(0, total_samples, total_samples, overlap_samples)]

    # Collect silence gaps between non-silent intervals
    cut_candidates = [0]
    for i in range(1, len(non_silent)):
        gap_start = non_silent[i - 1][1]
        gap_end = non_silent[i][0]
        if gap_end - gap_start >= min_silence_samples:
            cut_candidates.append((gap_start + gap_end) // 2)
    cut_candidates.append(total_samples)

    # Enforce max_segment_sec by subdividing long segments
    boundaries = [cut_candidates[0]]
    for i in range(1, len(cut_candidates)):
        seg_len = cut_candidates[i] - boundaries[-1]
        if seg_len > max_segment_samples:
            n_extra = seg_len // max_segment_samples
            for j in range(1, n_extra + 1):
                mid = boundaries[-1] + j * max_segment_samples
                if mid < cut_candidates[i]:
                    boundaries.append(mid)
        boundaries.append(cut_candidates[i])

    boundaries = sorted(set(boundaries))

    return [
        _make_segment(boundaries[i], boundaries[i + 1], total_samples, overlap_samples)
        for i in range(len(boundaries) - 1)
    ]


def _make_segment(start: int, end: int, total: int, overlap: int) -> dict:
    return {
        "start": start,
        "end": end,
        "padded_start": max(0, start - overlap),
        "padded_end": min(total, end + overlap),
    }
