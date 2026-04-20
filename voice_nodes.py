"""
ComfyUI voice nodes — MisakaNodes/Voice category.

Lazy imports throughout: missing dependencies are reported at execution time,
not at ComfyUI startup.
"""

import os
import sys
import tempfile  # used only by _prepare_reference_wav
from pathlib import Path

# Ensure the plugin directory is on sys.path so `voice.*` sub-package imports work
sys.path.insert(0, str(Path(__file__).parent))

import folder_paths


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _get_audio_devices() -> list:
    try:
        from voice.realtime_stream import RealtimeVCStream
        names = [d["name"] for d in RealtimeVCStream.list_devices()]
        return names if names else ["Default"]
    except Exception:
        return ["Default"]


def _resolve_audio_path(path_str: str) -> Path:
    """
    Resolve an audio path that may be:
      - An absolute path typed by the user
      - A filename uploaded via ComfyUI's /upload/image endpoint
        (stored in ComfyUI/input/)
    """
    p = Path(path_str)
    if p.is_absolute() and p.exists():
        return p
    candidate = Path(folder_paths.get_input_directory()) / path_str
    if candidate.exists():
        return candidate
    return p  # returned as-is so callers can show a meaningful error


def _numpy_to_audio(audio, sr: int) -> dict:
    """Convert numpy float32 array (1D or 2D) to ComfyUI AUDIO dict."""
    import torch
    import numpy as np
    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim == 1:
        audio = audio[np.newaxis, :]          # (1, samples)
    tensor = torch.from_numpy(audio).unsqueeze(0)  # (1, channels, samples)
    return {"waveform": tensor, "sample_rate": sr}


def _prepare_reference_wav(path: Path) -> str:
    """Resample + mono-ify to 24 kHz WAV required by VoxCPM."""
    import soundfile as sf
    import numpy as np
    from voice.resampler import resample

    audio, sr = sf.read(str(path), always_2d=False)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    audio = audio.astype(np.float32)
    if sr != 24000:
        audio = resample(audio, sr, 24000)

    tmp = tempfile.NamedTemporaryFile(suffix="_vcpm_ref.wav", delete=False)
    sf.write(tmp.name, audio, 24000)
    return tmp.name


_INPUT_DEVICE_LIST = _get_audio_devices()
_OUTPUT_DEVICE_LIST = _get_audio_devices()

# Simple model cache so VoxCPM doesn't reload on every queue run
_VCPM_CACHE: dict = {}


# ===========================================================================
# ─── RVC Voice-Conversion nodes ────────────────────────────────────────────
# ===========================================================================

# ---------------------------------------------------------------------------
# Node 1: Load RVC Model
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
        if not model_path or not Path(model_path).exists():
            raise ValueError(f"[MisakaVC] Model file not found: {model_path}")

        from voice.rvc_wrapper import RVCConverter
        converter = RVCConverter(model_path=model_path, index_path=index_path, device=device)
        converter._default_f0_method = f0_method
        return (converter,)


# ---------------------------------------------------------------------------
# Node 2: Auto Parameters
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
        resolved = _resolve_audio_path(audio_path)
        if not resolved.exists():
            raise ValueError(f"[MisakaVC] Audio file not found: {audio_path}")

        from voice.auto_params import analyze_audio
        info = analyze_audio(str(resolved))

        vc_params = {
            "index_rate": info["recommended_index_rate"],
            "protect": info["recommended_protect"],
            "f0_up_key": 0,
            "filter_radius": 3,
            "model_sr": info["recommended_model_sr"],
        }
        mins, secs = int(info["duration"] // 60), info["duration"] % 60
        report = "\n".join([
            f"路徑: {resolved}",
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
        ])
        return (vc_params, report)


# ---------------------------------------------------------------------------
# Node 3: Batch Convert
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

    def convert(self, vc_model, audio_path, vc_params=None,
                f0_up_key=0, index_rate=0.6, protect=0.33, filter_radius=3,
                min_silence_ms=300, overlap_ms=150, fade_ms=100, max_segment_sec=15.0):
        import soundfile as sf
        import numpy as np
        from voice.segmentation import find_cut_points
        from voice.crossfade import concat_with_crossfade
        from voice.resampler import detect_sr, resample, choose_model_sr

        resolved = _resolve_audio_path(audio_path)
        if not resolved.exists():
            raise ValueError(f"[MisakaVC] Input audio not found: {audio_path}")

        if vc_params:
            f0_up_key    = vc_params.get("f0_up_key", f0_up_key)
            index_rate   = vc_params.get("index_rate", index_rate)
            protect      = vc_params.get("protect", protect)
            filter_radius= vc_params.get("filter_radius", filter_radius)

        f0_method = getattr(vc_model, "_default_f0_method", "harvest")

        src_sr = detect_sr(str(resolved))
        audio, _ = sf.read(str(resolved), always_2d=False)
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        audio = audio.astype(np.float32)

        model_sr = choose_model_sr(src_sr)
        if src_sr != model_sr:
            audio = resample(audio, src_sr, model_sr)

        cut_points = find_cut_points(audio, model_sr,
                                     min_silence_ms=min_silence_ms,
                                     max_segment_sec=max_segment_sec,
                                     overlap_ms=overlap_ms)

        converted_segments = []
        for cp in cut_points:
            segment = audio[cp["padded_start"]: cp["padded_end"]]
            out_audio, out_sr = vc_model.convert(
                segment, model_sr, f0_method=f0_method,
                f0_up_key=f0_up_key, index_rate=index_rate,
                protect=protect, filter_radius=filter_radius,
            )
            if out_sr != model_sr:
                out_audio = resample(out_audio, out_sr, model_sr)
            converted_segments.append(out_audio)

        final_audio = concat_with_crossfade(converted_segments, cut_points, model_sr, fade_ms=fade_ms)

        report = (f"完成\n輸入: {resolved}\n"
                  f"採樣率: {model_sr} Hz\n分段數: {len(cut_points)}\n"
                  f"輸出時長: {len(final_audio)/model_sr:.2f}s\n"
                  f"f0_method: {f0_method}  f0_up_key: {f0_up_key}\n"
                  f"index_rate: {index_rate}  protect: {protect}")
        return (_numpy_to_audio(final_audio, model_sr), report)


# ---------------------------------------------------------------------------
# Node 4: Realtime Start
# ---------------------------------------------------------------------------

class MisakaVCRealtimeStart:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "vc_model": ("VC_MODEL",),
                "input_device":  (_INPUT_DEVICE_LIST,  {"default": _INPUT_DEVICE_LIST[0]}),
                "output_device": (_OUTPUT_DEVICE_LIST, {"default": _OUTPUT_DEVICE_LIST[0]}),
            },
            "optional": {
                "vc_params":        ("VC_PARAMS",),
                "block_time_ms":    ("INT",   {"default": 250,  "min": 50,  "max": 1000}),
                "extra_context_ms": ("INT",   {"default": 2500, "min": 500, "max": 5000}),
                "f0_up_key":        ("INT",   {"default": 0,    "min": -12, "max": 12}),
                "f0_method": (["rmvpe", "harvest", "crepe"], {"default": "rmvpe"}),
            },
        }

    RETURN_TYPES = ("VC_STREAM", "STRING")
    RETURN_NAMES = ("stream_handle", "status")
    FUNCTION = "start"
    CATEGORY = "MisakaNodes/Voice"

    def start(self, vc_model, input_device, output_device, vc_params=None,
              block_time_ms=250, extra_context_ms=2500, f0_up_key=0, f0_method="rmvpe"):
        from voice.realtime_stream import RealtimeVCStream
        if vc_params:
            f0_up_key = vc_params.get("f0_up_key", f0_up_key)

        all_devs = RealtimeVCStream.list_devices()
        in_idx  = next((d["index"] for d in all_devs if d["name"] == input_device),  None)
        out_idx = next((d["index"] for d in all_devs if d["name"] == output_device), None)

        vc_model._rt_f0_up_key      = f0_up_key
        vc_model._default_f0_method = f0_method

        stream = RealtimeVCStream(converter=vc_model, input_device=in_idx,
                                  output_device=out_idx, block_time_ms=block_time_ms,
                                  extra_context_ms=extra_context_ms, f0_method=f0_method)
        stream.start()

        status = (f"串流已啟動\n輸入裝置: {input_device}\n輸出裝置: {output_device}\n"
                  f"block_time: {block_time_ms} ms  context: {extra_context_ms} ms\n"
                  f"f0_method: {f0_method}  f0_up_key: {f0_up_key}")
        return (stream, status)


# ---------------------------------------------------------------------------
# Node 5: Realtime Stop
# ---------------------------------------------------------------------------

class MisakaVCRealtimeStop:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {"stream_handle": ("VC_STREAM",)}}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("status",)
    FUNCTION = "stop"
    CATEGORY = "MisakaNodes/Voice"

    def stop(self, stream_handle):
        if stream_handle is None:
            return ("無效的 stream handle",)
        was_running = stream_handle.is_running()
        stream_handle.stop()
        return ("串流已停止。" if was_running else "串流本來就未在執行。",)


# ---------------------------------------------------------------------------
# Node 6: Audio Info
# ---------------------------------------------------------------------------

class MisakaVCAudioInfo:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {"audio_path": ("STRING", {"default": ""})}}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("info",)
    FUNCTION = "inspect"
    CATEGORY = "MisakaNodes/Voice"

    def inspect(self, audio_path):
        import soundfile as sf
        from voice.auto_params import analyze_audio

        resolved = _resolve_audio_path(audio_path)
        if not resolved.exists():
            raise ValueError(f"[MisakaVC] Audio file not found: {audio_path}")

        info    = analyze_audio(str(resolved))
        sf_info = sf.info(str(resolved))
        mins, secs = int(info["duration"] // 60), info["duration"] % 60
        ch = "mono" if sf_info.channels == 1 else f"{sf_info.channels}ch"

        return ("\n".join([
            f"路徑: {resolved}",
            f"時長: {mins}m {secs:.1f}s",
            f"採樣率: {info['sr']} Hz → 建議模型: {info['recommended_model_sr']} Hz",
            f"聲道: {sf_info.channels} ({ch})",
            f"SNR 估計: {info['snr_db']:.1f} dB",
            f"F0 範圍: {info['f0_range'][0]:.0f}~{info['f0_range'][1]:.0f} Hz",
        ]),)


# ===========================================================================
# ─── VoxCPM TTS + Voice-Cloning nodes ──────────────────────────────────────
# ===========================================================================

import re as _re

_SENTENCE_END_RE = _re.compile(r'[。！？…]+')


def _normalize_text(text: str) -> str:
    """Normalize newlines before TTS: paragraph breaks → 。, single newlines → remove."""
    text = _re.sub(r'\n{2,}', '。', text)   # paragraph break → sentence end
    text = _re.sub(r'\n', '', text)          # single newline → join
    return text.strip()


def _split_for_tts(text: str, split_threshold: int, min_chunk: int = 12) -> list:
    """
    Returns [(chunk_text, pause_sec), ...].
    - text <= split_threshold: single chunk, no split.
    - Splits only at sentence-ending punctuation (。！？…).
    - Chunks shorter than min_chunk are merged forward to avoid over-splitting.
    """
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

    # Merge short chunks forward
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


def _vcpm_synth_one(model, model_version: str, text: str, prepared_ref: str,
                    prompt_text: str, inference_timesteps: int, cfg_value: float):
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

    # Move to CPU before converting to numpy to free VRAM immediately
    if isinstance(raw, torch.Tensor):
        raw = raw.detach().cpu()
    audio = np.array(raw, dtype=np.float32)
    if audio.ndim > 1:
        audio = audio.squeeze()

    # Release any lingering CUDA cache from this inference pass
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    return audio


_VCPM_VERSION_TO_ID = {
    "VoxCPM2":   "openbmb/VoxCPM2",
    "VoxCPM1.5": "openbmb/VoxCPM1.5",
}


def _vcpm_load(model_version: str, model_id_override: str = "", ffmpeg_dll_dir: str = ""):
    """Load (or return cached) VoxCPM model."""
    dll_dir = ffmpeg_dll_dir or os.environ.get("FFMPEG_DLL_DIR", "")
    if dll_dir and os.path.isdir(dll_dir):
        os.add_dll_directory(dll_dir)

    try:
        import voxcpm
    except ImportError:
        raise RuntimeError(
            "[MisakaVCPM] voxcpm is not installed.\n"
            "Run: pip install voxcpm\n"
            "Windows also requires FFmpeg shared DLLs — set ffmpeg_dll_dir or FFMPEG_DLL_DIR."
        )

    model_id = model_id_override.strip() or _VCPM_VERSION_TO_ID[model_version]
    if model_id in _VCPM_CACHE:
        return _VCPM_CACHE[model_id], model_id

    print(f"[MisakaVCPM] Loading {model_id} …")
    model = voxcpm.VoxCPM.from_pretrained(model_id)
    _VCPM_CACHE[model_id] = model
    print(f"[MisakaVCPM] Model ready: {model_id}")
    return model, model_id


# ---------------------------------------------------------------------------
# Node 7: VoxCPM Generate (TTS + Voice Cloning)
# ---------------------------------------------------------------------------

class MisakaVCPMGenerate:
    """
    TTS + zero-shot voice cloning via VoxCPM.

    VoxCPM2   — only reference_audio needed (true zero-shot).
    VoxCPM1.5 — also needs prompt_text (the words spoken in reference_audio).

    Model is loaded on first run and cached; switching model_version reloads once.
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
                # VoxCPM1.5 only: transcript of the reference audio
                "prompt_text":         ("STRING", {"default": "", "multiline": False}),
                "inference_timesteps": ("INT",   {"default": 24,  "min": 1,   "max": 100}),
                "cfg_value":           ("FLOAT", {"default": 2.5, "min": 0.0, "max": 10.0, "step": 0.1}),
                "speed":               ("FLOAT", {"default": 1.0, "min": 0.5, "max": 2.0,  "step": 0.05}),
                # Long-text splitting: text longer than this will be split at sentence-ending
                # punctuation (。！？…) and synthesized in chunks. 0 = always split.
                "split_threshold":     ("INT",   {"default": 40,  "min": 0,   "max": 500}),
                # -1 = random each run
                "seed":                ("INT",   {"default": -1,  "min": -1,  "max": 2**31 - 1}),
            },
        }

    RETURN_TYPES = ("AUDIO", "STRING")
    RETURN_NAMES = ("audio", "info")
    FUNCTION = "generate"
    CATEGORY = "MisakaNodes/Voice"

    def generate(self, model_version, text, reference_audio,
                 prompt_text="", inference_timesteps=24, cfg_value=2.5, speed=1.0,
                 split_threshold=40, seed=-1):
        import numpy as np

        text = _normalize_text(text)
        if not text:
            raise ValueError("[MisakaVCPM] Text cannot be empty.")

        ref_path = _resolve_audio_path(reference_audio)
        if not ref_path.exists():
            raise ValueError(f"[MisakaVCPM] Reference audio not found: {reference_audio}")

        model, model_id = _vcpm_load(model_version)
        sr = getattr(getattr(model, "tts_model", None), "sample_rate", None) or 48000

        import torch, random, numpy as np
        actual_seed = seed if seed >= 0 else random.randint(0, 2**31 - 1)
        torch.manual_seed(actual_seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(actual_seed)
        np.random.seed(actual_seed % (2**32))

        prepared_ref = _prepare_reference_wav(ref_path)

        chunks = _split_for_tts(text, split_threshold)
        print(f"[MisakaVCPM] {len(text)} chars → {len(chunks)} chunk(s) | ref={ref_path.name}")

        try:
            parts = []
            for i, (chunk_text, pause_sec) in enumerate(chunks):
                if len(chunks) > 1:
                    print(f"[MisakaVCPM] Chunk {i+1}/{len(chunks)}: 「{chunk_text[:20]}…」")
                chunk_audio = _vcpm_synth_one(model, model_version, chunk_text, prepared_ref,
                                              prompt_text, inference_timesteps, cfg_value)
                parts.append(chunk_audio)
                if pause_sec > 0:
                    parts.append(np.zeros(int(sr * pause_sec), dtype=np.float32))
        finally:
            try:
                os.unlink(prepared_ref)
            except Exception:
                pass

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
            f"文字: {len(text)} 字  分段: {len(chunks)}",
            f"參考音訊: {ref_path.name}",
            f"採樣率: {sr} Hz  時長: {len(audio)/sr:.2f}s  速度: {speed:.2f}x",
            f"seed: {actual_seed}",
        ]
        if len(chunks) > 1:
            info_lines.append("分段內容: " + " / ".join(f"{len(c)}字" for c, _ in chunks))
        return (_numpy_to_audio(audio, sr), "\n".join(info_lines))


# ===========================================================================
# Mappings
# ===========================================================================

NODE_CLASS_MAPPINGS = {
    # RVC voice conversion
    "MisakaVCLoadModel":      MisakaVCLoadModel,
    "MisakaVCAutoParams":     MisakaVCAutoParams,
    "MisakaVCConvertBatch":   MisakaVCConvertBatch,
    "MisakaVCRealtimeStart":  MisakaVCRealtimeStart,
    "MisakaVCRealtimeStop":   MisakaVCRealtimeStop,
    "MisakaVCAudioInfo":      MisakaVCAudioInfo,
    # VoxCPM TTS + voice cloning
    "MisakaVCPMGenerate":     MisakaVCPMGenerate,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MisakaVCLoadModel":      "Misaka VC Load Model",
    "MisakaVCAutoParams":     "Misaka VC Auto Params",
    "MisakaVCConvertBatch":   "Misaka VC Convert Batch",
    "MisakaVCRealtimeStart":  "Misaka VC Realtime Start",
    "MisakaVCRealtimeStop":   "Misaka VC Realtime Stop",
    "MisakaVCAudioInfo":      "Misaka VC Audio Info",
    "MisakaVCPMGenerate":     "Misaka VCPM Generate (TTS)",
}
