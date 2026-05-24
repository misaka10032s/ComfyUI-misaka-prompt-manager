"""
Shared helpers for voice conversion nodes.
All voice node files import from this module.
"""
import os
import re as _re
import sys
import tempfile
from pathlib import Path

# Ensure the plugin root is on sys.path so `from voice.rvc_wrapper import ...` resolves.
# This file is at: nodes/voice/_shared.py  →  plugin root is 3 dirs up.
_PLUGIN_ROOT = str(Path(__file__).parent.parent.parent)
if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)

import folder_paths

_VCPM_CACHE: dict = {}

_SENTENCE_END_RE = _re.compile(r'[。！？…]+')


def _resolve_audio_path(path_str: str) -> Path:
    if not path_str or not path_str.strip():
        return Path("")
    p = Path(path_str)
    if p.is_absolute() and p.is_file():
        return p
    candidate = Path(folder_paths.get_input_directory()) / path_str
    if candidate.is_file():
        return candidate
    return p


def _numpy_to_audio(audio, sr: int) -> dict:
    import torch
    import numpy as np
    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim == 1:
        audio = audio[np.newaxis, :]
    tensor = torch.from_numpy(audio).unsqueeze(0)
    return {"waveform": tensor, "sample_rate": sr}


def _prepare_reference_wav(path: Path) -> str:
    """Resample + mono to 24 kHz WAV as required by VoxCPM."""
    import soundfile as sf
    import numpy as np
    import soxr

    audio, sr = sf.read(str(path), always_2d=False)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    audio = audio.astype(np.float32)
    if sr != 24000:
        audio = soxr.resample(audio, sr, 24000)

    tmp = tempfile.NamedTemporaryFile(suffix="_vcpm_ref.wav", delete=False)
    sf.write(tmp.name, audio, 24000)
    return tmp.name


def _normalize_text(text: str) -> str:
    text = _re.sub(r'\n{2,}', '。', text)
    text = _re.sub(r'\n', '', text)
    return text.strip()


def _split_for_tts(text: str, split_threshold: int, min_chunk: int = 12) -> list:
    if len(text) <= split_threshold:
        return [(text, 0.0)]

    PAUSE = 0.25
    raw = []
    pos = 0
    for m in _SENTENCE_END_RE.finditer(text):
        chunk = text[pos:m.end()].strip()
        if chunk:
            raw.append(chunk)
        pos = m.end()
    tail = text[pos:].strip()
    if tail:
        raw.append(tail)

    if len(raw) <= 1:
        return [(text, 0.0)]

    merged = []
    buf = ""
    for chunk in raw:
        buf = (buf + chunk) if buf else chunk
        if len(buf) >= min_chunk:
            merged.append(buf)
            buf = ""
    if buf:
        if merged:
            merged[-1] += buf
        else:
            merged.append(buf)

    return [(c, PAUSE if i < len(merged) - 1 else 0.0) for i, c in enumerate(merged)]


def _vcpm_load(model_version: str):
    dll_dir = os.environ.get("FFMPEG_DLL_DIR", "")
    if dll_dir and os.path.isdir(dll_dir):
        os.add_dll_directory(dll_dir)

    try:
        import voxcpm
    except ImportError:
        raise RuntimeError(
            "[MisakaVCPM] voxcpm is not installed. Run: pip install voxcpm\n"
            "Windows also requires FFmpeg shared DLLs — set FFMPEG_DLL_DIR env var."
        )

    model_id = {"VoxCPM2": "openbmb/VoxCPM2", "VoxCPM1.5": "openbmb/VoxCPM1.5"}[model_version]
    if model_id in _VCPM_CACHE:
        return _VCPM_CACHE[model_id], model_id

    print(f"[MisakaVCPM] Loading {model_id} …")
    model = voxcpm.VoxCPM.from_pretrained(model_id)
    _VCPM_CACHE[model_id] = model
    print(f"[MisakaVCPM] Model ready: {model_id}")
    return model, model_id


def _vcpm_synth_one(model, model_version, text, prepared_ref, prompt_text,
                    inference_timesteps, cfg_value):
    import torch
    import numpy as np

    with torch.no_grad():
        if model_version == "VoxCPM2":
            raw = model.generate(
                text=text,
                reference_wav_path=prepared_ref,
                inference_timesteps=inference_timesteps,
                cfg_value=cfg_value,
            )
        else:
            raw = model.generate(
                text=text,
                prompt_wav_path=prepared_ref,
                prompt_text=prompt_text,
                inference_timesteps=inference_timesteps,
                cfg_value=cfg_value,
            )

    if isinstance(raw, torch.Tensor):
        raw = raw.detach().cpu()
    audio = np.array(raw, dtype=np.float32)
    if audio.ndim > 1:
        audio = audio.squeeze()

    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    return audio
