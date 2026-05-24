import os
import tempfile
from pathlib import Path
from ._shared import (
    _resolve_audio_path, _numpy_to_audio,
    _prepare_reference_wav, _normalize_text,
    _split_for_tts, _vcpm_load, _vcpm_synth_one,
)


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
