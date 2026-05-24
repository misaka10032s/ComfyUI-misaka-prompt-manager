from pathlib import Path
from ._shared import _resolve_audio_path, _numpy_to_audio


class MisakaVCConvertBatch:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "vc_model":   ("VC_MODEL",),
                "audio_path": ("STRING", {"default": ""}),
            },
            "optional": {
                "vc_params":     ("VC_PARAMS",),
                "output_path":   ("STRING", {"default": ""}),
                "f0_up_key":     ("INT",   {"default": 0,    "min": -24,  "max": 24}),
                # Ultimate RVC defaults: index_rate=0.5, protect=0.33, volume_envelope=0.25
                "index_rate":    ("FLOAT", {"default": 0.5,  "min": 0.0,  "max": 1.0,  "step": 0.01}),
                "protect":       ("FLOAT", {"default": 0.33, "min": 0.0,  "max": 0.5,  "step": 0.01}),
                "rms_mix_rate":  ("FLOAT", {"default": 0.25, "min": 0.0,  "max": 1.0,  "step": 0.01}),
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
        index_rate=0.5,
        protect=0.33,
        rms_mix_rate=0.25,
    ):
        import soundfile as sf
        import numpy as np
        import soxr
        from voice.resampler import detect_sr

        p = _resolve_audio_path(audio_path)
        if not p.is_file():
            raise ValueError(f"[MisakaVC] Input audio not found: {audio_path}")
        audio_path_str = str(p)

        if vc_params:
            f0_up_key    = vc_params.get("f0_up_key",    f0_up_key)
            index_rate   = vc_params.get("index_rate",   index_rate)
            protect      = vc_params.get("protect",      protect)
            rms_mix_rate = vc_params.get("rms_mix_rate", rms_mix_rate)

        f0_method = getattr(vc_model, "_default_f0_method", "harvest")

        src_sr = detect_sr(audio_path_str)
        audio, _ = sf.read(audio_path_str, always_2d=False, dtype="float32")
        if audio.ndim > 1:
            audio = audio.mean(axis=1)

        out_audio, out_sr = vc_model.convert(
            audio, src_sr,
            f0_method=f0_method,
            f0_up_key=f0_up_key,
            index_rate=index_rate,
            protect=protect,
            rms_mix_rate=rms_mix_rate,
        )

        saved_note = ""
        _out = str(output_path).strip() if output_path else ""
        if _out and Path(_out).suffix.lower() in (".wav", ".flac", ".ogg", ".mp3"):
            Path(_out).parent.mkdir(parents=True, exist_ok=True)
            sf.write(_out, out_audio, out_sr)
            saved_note = f"\n輸出: {_out}"

        report = (
            f"完成\n"
            f"輸入: {audio_path_str}"
            f"{saved_note}\n"
            f"採樣率: {out_sr} Hz\n"
            f"輸出時長: {len(out_audio) / out_sr:.2f}s\n"
            f"f0_method: {f0_method}  f0_up_key: {f0_up_key}\n"
            f"index_rate: {index_rate}  protect: {protect}  rms_mix: {rms_mix_rate}"
        )
        return (_numpy_to_audio(out_audio, out_sr), report)
