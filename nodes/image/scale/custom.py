from ._shared import _ASPECT_RATIOS, _round8


class MisakaScaleCustom:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "aspect_ratio": (_ASPECT_RATIOS, {"default": "2:3"}),
                "width": ("INT", {"default": 512, "min": 0, "max": 8192, "step": 8}),
                "height": ("INT", {"default": 0, "min": 0, "max": 8192, "step": 8}),
                "scale": ("FLOAT", {"default": 1.5, "min": 1.0, "max": 8.0, "step": 0.25}),
            },
        }

    RETURN_TYPES = ("INT", "INT", "INT", "INT", "STRING")
    RETURN_NAMES = ("width", "height", "scaled_width", "scaled_height", "info")
    FUNCTION = "execute"
    CATEGORY = "MisakaNodes"

    def execute(self, aspect_ratio, width, height, scale):
        w, h = width, height

        if aspect_ratio != "free":
            rw, rh = map(int, aspect_ratio.split(":"))
            if w > 0 and h == 0:
                h = _round8(w * rh / rw)
            elif h > 0 and w == 0:
                w = _round8(h * rw / rh)
            # both > 0: JS Calculate already resolved them — use as-is

        if w == 0 or h == 0:
            raise ValueError(
                f"[MisakaImageScaleCustom] Cannot compute size: width={w}, height={h}. "
                "Set at least one dimension > 0, or click Calculate first."
            )

        sw, sh = _round8(w * scale), _round8(h * scale)
        info = f"{w}×{h}  →  {sw}×{sh}  ({scale:.2f}×)  [{aspect_ratio}]"
        return (w, h, sw, sh, info)
