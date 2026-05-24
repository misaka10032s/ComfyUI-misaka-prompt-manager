from .load_model import MisakaVCLoadModel
from .auto_params import MisakaVCAutoParams
from .convert_batch import MisakaVCConvertBatch
from .audio_info import MisakaVCAudioInfo
from .pm_generate import MisakaVCPMGenerate

NODE_CLASS_MAPPINGS = {
    "MisakaVCLoadModel":    MisakaVCLoadModel,
    "MisakaVCAutoParams":   MisakaVCAutoParams,
    "MisakaVCConvertBatch": MisakaVCConvertBatch,
    "MisakaVCAudioInfo":    MisakaVCAudioInfo,
    "MisakaVCPMGenerate":   MisakaVCPMGenerate,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MisakaVCLoadModel":    "Misaka VC Load Model",
    "MisakaVCAutoParams":   "Misaka VC Auto Params",
    "MisakaVCConvertBatch": "Misaka VC Convert Batch",
    "MisakaVCAudioInfo":    "Misaka VC Audio Info",
    "MisakaVCPMGenerate":   "Misaka VCPM Generate (TTS)",
}
