"""
ComfyUI voice-conversion nodes — MisakaNodes/Voice category.

All nodes use lazy imports so missing audio dependencies do not crash ComfyUI
at startup; errors are reported when the node is actually executed.
"""

from pathlib import Path


def _get_audio_devices() -> list:
    """Return device name list for COMBO widgets (called at class-definition time)."""
    try:
        from voice.realtime_stream import RealtimeVCStream
        devs = RealtimeVCStream.list_devices()
        names = [d["name"] for d in devs]
        return names if names else ["Default"]
    except Exception:
        return ["Default"]


_INPUT_DEVICE_LIST = _get_audio_devices()
_OUTPUT_DEVICE_LIST = _get_audio_devices()


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
        converter = RVCConverter(
            model_path=model_path,
            index_path=index_path,
            device=device,
        )
        # Store selected f0_method on instance for downstream nodes
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
        if not audio_path or not Path(audio_path).exists():
            raise ValueError(f"[MisakaVC] Audio file not found: {audio_path}")

        from voice.auto_params import analyze_audio
        info = analyze_audio(audio_path)

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
            f"路徑: {audio_path}",
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
# Node 3: Batch Convert
# ---------------------------------------------------------------------------

class MisakaVCConvertBatch:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "vc_model": ("VC_MODEL",),
                "audio_path": ("STRING", {"default": ""}),
                "output_path": ("STRING", {"default": ""}),
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

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("output_path", "report")
    FUNCTION = "convert"
    CATEGORY = "MisakaNodes/Voice"

    def convert(
        self,
        vc_model,
        audio_path,
        output_path,
        vc_params=None,
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

        if not audio_path or not Path(audio_path).exists():
            raise ValueError(f"[MisakaVC] Input audio not found: {audio_path}")

        # vc_params takes priority over manual sliders
        if vc_params:
            f0_up_key = vc_params.get("f0_up_key", f0_up_key)
            index_rate = vc_params.get("index_rate", index_rate)
            protect = vc_params.get("protect", protect)
            filter_radius = vc_params.get("filter_radius", filter_radius)

        f0_method = getattr(vc_model, "_default_f0_method", "harvest")

        # 1. Load and resample to model sr
        src_sr = detect_sr(audio_path)
        audio, _ = __import__("soundfile").read(audio_path, always_2d=False)
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        audio = audio.astype(np.float32)

        model_sr = choose_model_sr(src_sr)
        if src_sr != model_sr:
            audio = resample(audio, src_sr, model_sr)

        # 2. Find cut points
        cut_points = find_cut_points(
            audio, model_sr,
            min_silence_ms=min_silence_ms,
            max_segment_sec=max_segment_sec,
            overlap_ms=overlap_ms,
        )

        # 3. Convert each segment
        converted_segments = []
        for i, cp in enumerate(cut_points):
            segment = audio[cp["padded_start"]: cp["padded_end"]]
            out_audio, out_sr = vc_model.convert(
                segment, model_sr,
                f0_method=f0_method,
                f0_up_key=f0_up_key,
                index_rate=index_rate,
                protect=protect,
                filter_radius=filter_radius,
            )
            # Resample back to model_sr if converter changed it
            if out_sr != model_sr:
                out_audio = resample(out_audio, out_sr, model_sr)
            converted_segments.append(out_audio)

        # 4. Stitch with cross-fade
        final_audio = concat_with_crossfade(converted_segments, cut_points, model_sr, fade_ms=fade_ms)

        # 5. Write output (maintain model sr — no post-downsampling)
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        sf.write(output_path, final_audio, model_sr)

        report = (
            f"完成\n"
            f"輸入: {audio_path}\n"
            f"輸出: {output_path}\n"
            f"採樣率: {model_sr} Hz\n"
            f"分段數: {len(cut_points)}\n"
            f"輸出時長: {len(final_audio) / model_sr:.2f}s\n"
            f"f0_method: {f0_method}  f0_up_key: {f0_up_key}\n"
            f"index_rate: {index_rate}  protect: {protect}"
        )
        return (output_path, report)


# ---------------------------------------------------------------------------
# Node 4: Realtime Start
# ---------------------------------------------------------------------------

class MisakaVCRealtimeStart:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "vc_model": ("VC_MODEL",),
                "input_device": (_INPUT_DEVICE_LIST, {"default": _INPUT_DEVICE_LIST[0]}),
                "output_device": (_OUTPUT_DEVICE_LIST, {"default": _OUTPUT_DEVICE_LIST[0]}),
            },
            "optional": {
                "vc_params": ("VC_PARAMS",),
                "block_time_ms": ("INT", {"default": 250, "min": 50, "max": 1000}),
                "extra_context_ms": ("INT", {"default": 2500, "min": 500, "max": 5000}),
                "f0_up_key": ("INT", {"default": 0, "min": -12, "max": 12}),
                "f0_method": (["rmvpe", "harvest", "crepe"], {"default": "rmvpe"}),
            },
        }

    RETURN_TYPES = ("VC_STREAM", "STRING")
    RETURN_NAMES = ("stream_handle", "status")
    FUNCTION = "start"
    CATEGORY = "MisakaNodes/Voice"

    def start(
        self,
        vc_model,
        input_device,
        output_device,
        vc_params=None,
        block_time_ms=250,
        extra_context_ms=2500,
        f0_up_key=0,
        f0_method="rmvpe",
    ):
        from voice.realtime_stream import RealtimeVCStream

        if vc_params:
            f0_up_key = vc_params.get("f0_up_key", f0_up_key)

        # Resolve device names back to indices
        all_devs = RealtimeVCStream.list_devices()
        in_idx = next((d["index"] for d in all_devs if d["name"] == input_device), None)
        out_idx = next((d["index"] for d in all_devs if d["name"] == output_device), None)

        # Apply f0_up_key to the converter (mutate temporarily — stream inherits it)
        vc_model._rt_f0_up_key = f0_up_key
        vc_model._default_f0_method = f0_method

        stream = RealtimeVCStream(
            converter=vc_model,
            input_device=in_idx,
            output_device=out_idx,
            block_time_ms=block_time_ms,
            extra_context_ms=extra_context_ms,
            f0_method=f0_method,
        )
        stream.start()

        status = (
            f"串流已啟動\n"
            f"輸入裝置: {input_device}\n"
            f"輸出裝置: {output_device}\n"
            f"block_time: {block_time_ms} ms  context: {extra_context_ms} ms\n"
            f"f0_method: {f0_method}  f0_up_key: {f0_up_key}"
        )
        return (stream, status)


# ---------------------------------------------------------------------------
# Node 5: Realtime Stop
# ---------------------------------------------------------------------------

class MisakaVCRealtimeStop:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "stream_handle": ("VC_STREAM",),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("status",)
    FUNCTION = "stop"
    CATEGORY = "MisakaNodes/Voice"

    def stop(self, stream_handle):
        if stream_handle is None:
            return ("無效的 stream handle",)
        was_running = stream_handle.is_running()
        stream_handle.stop()
        status = "串流已停止。" if was_running else "串流本來就未在執行。"
        return (status,)


# ---------------------------------------------------------------------------
# Node 6: Audio Info
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
        if not audio_path or not Path(audio_path).exists():
            raise ValueError(f"[MisakaVC] Audio file not found: {audio_path}")

        from voice.auto_params import analyze_audio
        from voice.resampler import choose_model_sr
        import soundfile as sf

        info = analyze_audio(audio_path)
        sf_info = sf.info(audio_path)

        mins = int(info["duration"] // 60)
        secs = info["duration"] % 60
        channels = "mono" if sf_info.channels == 1 else f"{sf_info.channels}ch"

        lines = [
            f"路徑: {audio_path}",
            f"時長: {mins}m {secs:.1f}s",
            f"採樣率: {info['sr']} Hz → 建議模型: {info['recommended_model_sr']} Hz",
            f"聲道: {sf_info.channels} ({channels})",
            f"SNR 估計: {info['snr_db']:.1f} dB",
            f"F0 範圍: {info['f0_range'][0]:.0f}~{info['f0_range'][1]:.0f} Hz",
        ]
        return ("\n".join(lines),)


# ---------------------------------------------------------------------------
# Mappings
# ---------------------------------------------------------------------------

NODE_CLASS_MAPPINGS = {
    "MisakaVCLoadModel": MisakaVCLoadModel,
    "MisakaVCAutoParams": MisakaVCAutoParams,
    "MisakaVCConvertBatch": MisakaVCConvertBatch,
    "MisakaVCRealtimeStart": MisakaVCRealtimeStart,
    "MisakaVCRealtimeStop": MisakaVCRealtimeStop,
    "MisakaVCAudioInfo": MisakaVCAudioInfo,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MisakaVCLoadModel": "Misaka VC Load Model",
    "MisakaVCAutoParams": "Misaka VC Auto Params",
    "MisakaVCConvertBatch": "Misaka VC Convert Batch",
    "MisakaVCRealtimeStart": "Misaka VC Realtime Start",
    "MisakaVCRealtimeStop": "Misaka VC Realtime Stop",
    "MisakaVCAudioInfo": "Misaka VC Audio Info",
}
