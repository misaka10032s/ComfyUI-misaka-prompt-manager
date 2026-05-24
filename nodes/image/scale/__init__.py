from .preset import MisakaScalePreset
from .custom import MisakaScaleCustom

NODE_CLASS_MAPPINGS = {
    "MisakaScalePreset": MisakaScalePreset,
    "MisakaScaleCustom": MisakaScaleCustom,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MisakaScalePreset": "Misaka Scale Preset",
    "MisakaScaleCustom": "Misaka Scale Custom",
}
