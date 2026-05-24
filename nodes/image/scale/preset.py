from ._shared import _SCALE_PRESETS, _round8, _parse_preset


class MisakaScalePreset:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "preset": (_SCALE_PRESETS, {"default": _SCALE_PRESETS[1]}),
                "scale": ("FLOAT", {"default": 1.5, "min": 1.0, "max": 8.0, "step": 0.25}),
            },
        }

    RETURN_TYPES = ("INT", "INT", "INT", "INT", "STRING")
    RETURN_NAMES = ("width", "height", "scaled_width", "scaled_height", "info")
    FUNCTION = "execute"
    CATEGORY = "MisakaNodes"

    def execute(self, preset, scale):
        w, h = _parse_preset(preset)
        sw, sh = _round8(w * scale), _round8(h * scale)
        info = f"{w}×{h}  →  {sw}×{sh}  ({scale:.2f}×)"
        return (w, h, sw, sh, info)
