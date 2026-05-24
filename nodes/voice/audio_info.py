from ._shared import _resolve_audio_path


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
