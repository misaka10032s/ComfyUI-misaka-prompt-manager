import numpy as np
from pathlib import Path


def analyze_audio(path: str) -> dict:
    """
    Analyse audio and return recommended RVC parameters.

    Returns a dict with sr, duration, snr_db, is_speech, f0_range,
    recommended_model_sr, recommended_index_rate, recommended_protect, note.
    """
    import librosa
    import soundfile as sf
    from .resampler import choose_model_sr

    path = str(Path(path))
    audio, sr = librosa.load(path, sr=None, mono=True)
    duration = len(audio) / sr
    channels = sf.info(path).channels

    snr_db = _estimate_snr(audio, sr)
    rms = float(np.sqrt(np.mean(audio ** 2)))
    is_speech = rms > 0.01

    hop_length = recommend_hop_length(duration, sr)
    f0_range = _estimate_f0_range(audio, sr, hop_length)

    recommended_model_sr = choose_model_sr(sr)
    index_rate, protect, note = _recommend_params(snr_db, f0_range)

    return {
        "sr": sr,
        "duration": duration,
        "snr_db": snr_db,
        "is_speech": is_speech,
        "f0_range": f0_range,
        "recommended_model_sr": recommended_model_sr,
        "recommended_index_rate": index_rate,
        "recommended_protect": protect,
        "note": note,
    }


def recommend_hop_length(duration_sec: float, sr: int) -> int:
    """Smaller hop for short audio (high F0 resolution); larger for long (speed)."""
    if duration_sec < 5:
        return 128
    if duration_sec < 30:
        return 256
    return 512


def _estimate_snr(audio: np.ndarray, sr: int) -> float:
    import librosa
    rms = librosa.feature.rms(y=audio, frame_length=2048, hop_length=512)[0]
    rms_db = librosa.amplitude_to_db(rms + 1e-9)
    if len(rms_db) < 4:
        return 30.0
    loud = rms_db[rms_db > np.percentile(rms_db, 75)]
    quiet = rms_db[rms_db < np.percentile(rms_db, 25)]
    if len(loud) == 0 or len(quiet) == 0:
        return 30.0
    return float(np.mean(loud) - np.mean(quiet))


def _estimate_f0_range(audio: np.ndarray, sr: int, hop_length: int) -> tuple:
    try:
        import librosa
        f0 = librosa.yin(audio, fmin=50.0, fmax=800.0, sr=sr, hop_length=hop_length)
        valid = f0[(f0 > 50) & (f0 < 800)]
        if len(valid) > 10:
            return (float(np.percentile(valid, 5)), float(np.percentile(valid, 95)))
    except Exception:
        pass
    return (100.0, 400.0)


def _recommend_params(snr_db: float, f0_range: tuple) -> tuple:
    f0_variance = f0_range[1] - f0_range[0]
    high_f0_variance = f0_variance > 200  # Japanese speech tends wider range

    if snr_db < 20:
        index_rate, protect = 0.3, 0.45
        note = f"SNR {snr_db:.1f} dB 低（雜訊多），使用較低 index_rate 與較高 protect"
    elif snr_db <= 40:
        index_rate, protect = 0.6, 0.33
        note = f"SNR {snr_db:.1f} dB 中等，使用標準參數"
    else:
        index_rate, protect = 0.75, 0.25
        note = f"SNR {snr_db:.1f} dB 高（乾淨），使用較高 index_rate"

    if high_f0_variance:
        protect = min(0.5, protect + 0.05)
        note += f"；F0 變化大（{f0_range[0]:.0f}~{f0_range[1]:.0f} Hz），提高 protect"

    return index_rate, protect, note
