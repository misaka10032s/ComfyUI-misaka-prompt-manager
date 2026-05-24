from ._shared import _resolve_audio_path


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
