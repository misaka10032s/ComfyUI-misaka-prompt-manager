from pathlib import Path
from ._shared import _resolve_audio_path


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
