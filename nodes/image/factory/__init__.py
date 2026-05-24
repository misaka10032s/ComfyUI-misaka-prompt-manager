from .profile_factory import MisakaImageProfileFactory
from .prompt_manager import MisakaImagePromptManager
from .prompt_builder import MisakaImagePromptBuilder
from ._shared import get_storage_path  # re-export for __init__.py API route

NODE_CLASS_MAPPINGS = {
    "MisakaImageProfileFactory": MisakaImageProfileFactory,
    "MisakaImagePromptManager":  MisakaImagePromptManager,
    "MisakaImagePromptBuilder":  MisakaImagePromptBuilder,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MisakaImageProfileFactory": "Misaka Image Profile Factory (Editor/Saver)",
    "MisakaImagePromptManager":  "Misaka Image Prompt Manager (Loader)",
    "MisakaImagePromptBuilder":  "Misaka Image Prompt Builder (Multi-Concat)",
}
