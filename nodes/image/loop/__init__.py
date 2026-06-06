from .prompt_input import MisakaLoopPrompt
from .ckpt_input import MisakaLoopCkpt
from .loop_ckpt_core import MisakaLoopCkptCore
from .loop_prompt_core import MisakaLoopPromptCore
from .loop_path_manager import MisakaLoopPathManager

NODE_CLASS_MAPPINGS = {
    "MisakaLoopPrompt":       MisakaLoopPrompt,
    "MisakaLoopCkpt":         MisakaLoopCkpt,
    "MisakaLoopCkptCore":     MisakaLoopCkptCore,
    "MisakaLoopPromptCore":   MisakaLoopPromptCore,
    "MisakaLoopPathManager":  MisakaLoopPathManager,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MisakaLoopPrompt":       "Misaka Loop Prompt",
    "MisakaLoopCkpt":         "Misaka Loop Ckpt",
    "MisakaLoopCkptCore":     "Misaka Loop Ckpt Core",
    "MisakaLoopPromptCore":   "Misaka Loop Prompt Core",
    "MisakaLoopPathManager":  "Misaka Loop Path Manager",
}
