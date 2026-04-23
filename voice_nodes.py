"""
ComfyUI voice nodes — MisakaNodes/Voice category.
Batch voice conversion (RVC) + TTS/voice cloning (VoxCPM).
"""

import os
import re as _re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import folder_paths

_VCPM_CACHE: dict = {}

_SENTENCE_END_RE = _re.compile(r'[。！？…]+')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Node: Load RVC Model
# ---------------------------------------------------------------------------

class MisakaVCLoadModel:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "model_path": ("STRING", {"default": ""}),
                "f0_method": (["harvest", "crepe", "rmvpe"], {"default": "harvest"}),
                "device": (["cuda", "cpu"], {"default": "cuda"}),
            },
            "optional": {
                "index_path": ("STRING", {"default": ""}),
            },
        }

    RETURN_TYPES = ("VC_MODEL",)
    RETURN_NAMES = ("vc_model",)
    FUNCTION = "load"
    CATEGORY = "MisakaNodes/Voice"

    def load(self, model_path, f0_method, device, index_path=""):
        p = _resolve_audio_path(model_path)
        if not p.is_file():
            raise ValueError(f"[MisakaVC] Model file not found: {model_path}")

        idx_p = _resolve_audio_path(index_path) if index_path and index_path.strip() else Path("")

        from voice.rvc_wrapper import RVCConverter
        converter = RVCConverter(
            model_path=str(p),
            index_path=str(idx_p) if idx_p.is_file() else "",
            device=device,
        )
        converter._default_f0_method = f0_method
        return (converter,)


# ---------------------------------------------------------------------------
# Node: Auto Parameters
# ---------------------------------------------------------------------------

class MisakaVCAutoParams:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "audio_path": ("STRING", {"default": ""}),
            },
        }

    RETURN_TYPES = ("VC_PARAMS", "STRING")
    RETURN_NAMES = ("vc_params", "analysis_report")
    FUNCTION = "analyze"
    CATEGORY = "MisakaNodes/Voice"

    def analyze(self, audio_path):
        p = _resolve_audio_path(audio_path)
        if not p.is_file():
            raise ValueError(f"[MisakaVC] Audio file not found: {audio_path}")

        from voice.auto_params import analyze_audio
        info = analyze_audio(str(p))

        vc_params = {
            "index_rate": info["recommended_index_rate"],
            "protect": info["recommended_protect"],
            "f0_up_key": 0,
            "filter_radius": 3,
            "model_sr": info["recommended_model_sr"],
        }

        mins = int(info["duration"] // 60)
        secs = info["duration"] % 60
        report_lines = [
            f"路徑: {p}",
            f"時長: {mins}m {secs:.1f}s",
            f"採樣率: {info['sr']} Hz → 建議模型: {info['recommended_model_sr']} Hz",
            f"SNR 估計: {info['snr_db']:.1f} dB",
            f"F0 範圍: {info['f0_range'][0]:.0f}~{info['f0_range'][1]:.0f} Hz",
            f"是否語音: {'是' if info['is_speech'] else '否'}",
            "",
            f"建議 index_rate: {vc_params['index_rate']}",
            f"建議 protect: {vc_params['protect']}",
            "",
            f"說明: {info['note']}",
        ]
        return (vc_params, "\n".join(report_lines))


# ---------------------------------------------------------------------------
# Node: Batch Convert
# ---------------------------------------------------------------------------

class MisakaVCConvertBatch:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "vc_model": ("VC_MODEL",),
                "audio_path": ("STRING", {"default": ""}),
            },
            "optional": {
                "vc_params": ("VC_PARAMS",),
                "output_path": ("STRING", {"default": ""}),
                "f0_up_key": ("INT", {"default": 0, "min": -12, "max": 12}),
                "index_rate": ("FLOAT", {"default": 0.6, "min": 0.0, "max": 1.0, "step": 0.01}),
                "protect": ("FLOAT", {"default": 0.33, "min": 0.0, "max": 0.5, "step": 0.01}),
                "filter_radius": ("INT", {"default": 3, "min": 0, "max": 7}),
                "min_silence_ms": ("INT", {"default": 300, "min": 100, "max": 2000}),
                "overlap_ms": ("INT", {"default": 150, "min": 50, "max": 500}),
                "fade_ms": ("INT", {"default": 100, "min": 10, "max": 300}),
                "max_segment_sec": ("FLOAT", {"default": 15.0, "min": 3.0, "max": 60.0}),
            },
        }

    RETURN_TYPES = ("AUDIO", "STRING")
    RETURN_NAMES = ("audio", "report")
    FUNCTION = "convert"
    CATEGORY = "MisakaNodes/Voice"

    def convert(
        self,
        vc_model,
        audio_path,
        vc_params=None,
        output_path="",
        f0_up_key=0,
        index_rate=0.6,
        protect=0.33,
        filter_radius=3,
        min_silence_ms=300,
        overlap_ms=150,
        fade_ms=100,
        max_segment_sec=15.0,
    ):
        import soundfile as sf
        import numpy as np
        from voice.segmentation import find_cut_points
        from voice.crossfade import concat_with_crossfade
        from voice.resampler import detect_sr, resample, choose_model_sr

        p = _resolve_audio_path(audio_path)
        if not p.is_file():
            raise ValueError(f"[MisakaVC] Input audio not found: {audio_path}")
        audio_path_str = str(p)

        if vc_params:
            f0_up_key = vc_params.get("f0_up_key", f0_up_key)
            index_rate = vc_params.get("index_rate", index_rate)
            protect = vc_params.get("protect", protect)
            filter_radius = vc_params.get("filter_radius", filter_radius)

        f0_method = getattr(vc_model, "_default_f0_method", "harvest")

        src_sr = detect_sr(audio_path_str)
        audio, _ = sf.read(audio_path_str, always_2d=False, dtype="float32")
        if audio.ndim > 1:
            audio = audio.mean(axis=1)

        model_sr = choose_model_sr(src_sr)
        if src_sr != model_sr:
            audio = resample(audio, src_sr, model_sr)

        cut_points = find_cut_points(
            audio, model_sr,
            min_silence_ms=min_silence_ms,
            max_segment_sec=max_segment_sec,
            overlap_ms=overlap_ms,
        )

        converted_segments = []
        for cp in cut_points:
            segment = audio[cp["padded_start"]: cp["padded_end"]]
            out_audio, out_sr = vc_model.convert(
                segment, model_sr,
                f0_method=f0_method,
                f0_up_key=f0_up_key,
                index_rate=index_rate,
                protect=protect,
                filter_radius=filter_radius,
            )
            if out_sr != model_sr:
                out_audio = resample(out_audio, out_sr, model_sr)
            converted_segments.append(out_audio)

        final_audio = concat_with_crossfade(converted_segments, cut_points, model_sr, fade_ms=fade_ms)

        saved_note = ""
        _out = str(output_path).strip() if output_path else ""
        if _out and Path(_out).suffix.lower() in (".wav", ".flac", ".ogg", ".mp3"):
            Path(_out).parent.mkdir(parents=True, exist_ok=True)
            sf.write(_out, final_audio, model_sr)
            saved_note = f"\n輸出: {_out}"

        report = (
            f"完成\n"
            f"輸入: {audio_path_str}"
            f"{saved_note}\n"
            f"採樣率: {model_sr} Hz\n"
            f"分段數: {len(cut_points)}\n"
            f"輸出時長: {len(final_audio) / model_sr:.2f}s\n"
            f"f0_method: {f0_method}  f0_up_key: {f0_up_key}\n"
            f"index_rate: {index_rate}  protect: {protect}"
        )
        return (_numpy_to_audio(final_audio, model_sr), report)


# ---------------------------------------------------------------------------
# Node: Audio Info
# ---------------------------------------------------------------------------

class MisakaVCAudioInfo:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "audio_path": ("STRING", {"default": ""}),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("info",)
    FUNCTION = "inspect"
    CATEGORY = "MisakaNodes/Voice"

    def inspect(self, audio_path):
        p = _resolve_audio_path(audio_path)
        if not p.is_file():
            raise ValueError(f"[MisakaVC] Audio file not found: {audio_path}")

        from voice.auto_params import analyze_audio
        import soundfile as sf

        info = analyze_audio(str(p))
        sf_info = sf.info(str(p))

        mins = int(info["duration"] // 60)
        secs = info["duration"] % 60
        channels = "mono" if sf_info.channels == 1 else f"{sf_info.channels}ch"

        lines = [
            f"路徑: {p}",
            f"時長: {mins}m {secs:.1f}s",
            f"採樣率: {info['sr']} Hz → 建議模型: {info['recommended_model_sr']} Hz",
            f"聲道: {sf_info.channels} ({channels})",
            f"SNR 估計: {info['snr_db']:.1f} dB",
            f"F0 範圍: {info['f0_range'][0]:.0f}~{info['f0_range'][1]:.0f} Hz",
        ]
        return ("\n".join(lines),)


# ---------------------------------------------------------------------------
# Node: VoxCPM Generate (TTS + Voice Cloning)
# ---------------------------------------------------------------------------

class MisakaVCPMGenerate:
    """
    TTS + zero-shot voice cloning via VoxCPM.
    VoxCPM2   — reference_audio only (true zero-shot).
    VoxCPM1.5 — also needs prompt_text (transcript of reference_audio).
    Model is cached after first load.
    """

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "model_version":   (["VoxCPM2", "VoxCPM1.5"], {"default": "VoxCPM2"}),
                "text":            ("STRING", {"multiline": True, "default": ""}),
                "reference_audio": ("STRING", {"default": ""}),
            },
            "optional": {
                "prompt_text":         ("STRING", {"default": "", "multiline": False}),
                "inference_timesteps": ("INT",   {"default": 24,  "min": 1,   "max": 100}),
                "cfg_value":           ("FLOAT", {"default": 2.5, "min": 0.0, "max": 10.0, "step": 0.1}),
                "speed":               ("FLOAT", {"default": 1.0, "min": 0.5, "max": 2.0,  "step": 0.05}),
                "split_threshold":     ("INT",   {"default": 40,  "min": 0,   "max": 500}),
                "seed":                ("INT",   {"default": -1,  "min": -1,  "max": 2**31 - 1}),
            },
        }

    RETURN_TYPES = ("AUDIO", "STRING")
    RETURN_NAMES = ("audio", "info")
    FUNCTION = "generate"
    CATEGORY = "MisakaNodes/Voice"

    def generate(self, model_version, text, reference_audio,
                 prompt_text="", inference_timesteps=24, cfg_value=2.5,
                 speed=1.0, split_threshold=40, seed=-1):
        import random
        import torch
        import numpy as np
        import soundfile as sf

        text = _normalize_text(text)
        if not text:
            raise ValueError("[MisakaVCPM] Text cannot be empty.")

        ref_path = _resolve_audio_path(reference_audio)
        if not ref_path.is_file():
            raise ValueError(f"[MisakaVCPM] Reference audio not found: {reference_audio}")

        model, model_id = _vcpm_load(model_version)
        sr = getattr(getattr(model, "tts_model", None), "sample_rate", None) or 48000

        actual_seed = seed if seed >= 0 else random.randint(0, 2**31 - 1)
        torch.manual_seed(actual_seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(actual_seed)
        np.random.seed(actual_seed % (2**32))

        prepared_ref = _prepare_reference_wav(ref_path)

        chunks = _split_for_tts(text, split_threshold)
        n = len(chunks)
        print(f"[MisakaVCPM] {len(text)} chars → {n} chunk(s) | ref={ref_path.name}")
        if n > 20:
            print(f"[MisakaVCPM] WARNING: {n} chunks — this will take a long time.")

        tmp_files = []
        try:
            for i, (chunk_text, pause_sec) in enumerate(chunks):
                if n > 1:
                    print(f"[MisakaVCPM] Chunk {i+1}/{n}: {len(chunk_text)} chars")
                chunk_audio = _vcpm_synth_one(model, model_version, chunk_text,
                                              prepared_ref, prompt_text,
                                              inference_timesteps, cfg_value)
                fd, tmp_path = tempfile.mkstemp(suffix=f"_vcpm_{i}.wav")
                os.close(fd)
                sf.write(tmp_path, chunk_audio, sr)
                tmp_files.append((tmp_path, pause_sec))
                del chunk_audio
        finally:
            try:
                os.unlink(prepared_ref)
            except Exception:
                pass

        parts = []
        for tmp_path, pause_sec in tmp_files:
            chunk_audio, _ = sf.read(tmp_path, dtype="float32")
            parts.append(chunk_audio)
            if pause_sec > 0:
                parts.append(np.zeros(int(sr * pause_sec), dtype=np.float32))
            os.unlink(tmp_path)

        audio = np.concatenate(parts) if len(parts) > 1 else parts[0]
        peak = np.max(np.abs(audio))
        if peak > 1.0:
            audio = audio / peak

        if abs(speed - 1.0) > 0.02:
            import librosa
            audio = librosa.effects.time_stretch(audio, rate=float(speed))

        info_lines = [
            "完成",
            f"模型: {model_id}",
            f"文字: {len(text)} 字  分段: {n}",
            f"參考音訊: {ref_path.name}",
            f"採樣率: {sr} Hz  時長: {len(audio)/sr:.2f}s  速度: {speed:.2f}x",
            f"seed: {actual_seed}",
        ]
        if n > 1:
            info_lines.append("分段: " + " / ".join(f"{len(c)}字" for c, _ in chunks))
        return (_numpy_to_audio(audio, sr), "\n".join(info_lines))


# ===========================================================================
# Mappings
# ===========================================================================

NODE_CLASS_MAPPINGS = {
    "MisakaVCLoadModel":    MisakaVCLoadModel,
    "MisakaVCAutoParams":   MisakaVCAutoParams,
    "MisakaVCConvertBatch": MisakaVCConvertBatch,
    "MisakaVCAudioInfo":    MisakaVCAudioInfo,
    "MisakaVCPMGenerate":   MisakaVCPMGenerate,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MisakaVCLoadModel":    "Misaka VC Load Model",
    "MisakaVCAutoParams":   "Misaka VC Auto Params",
    "MisakaVCConvertBatch": "Misaka VC Convert Batch",
    "MisakaVCAudioInfo":    "Misaka VC Audio Info",
    "MisakaVCPMGenerate":   "Misaka VCPM Generate (TTS)",
}
