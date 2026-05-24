from .image import NODE_CLASS_MAPPINGS as _IMAGE_NODES, NODE_DISPLAY_NAME_MAPPINGS as _IMAGE_NAMES

try:
    from .voice import NODE_CLASS_MAPPINGS as _VOICE_NODES, NODE_DISPLAY_NAME_MAPPINGS as _VOICE_NAMES
except Exception as e:
    print(f"[MisakaVC] Could not load voice nodes: {e}")
    _VOICE_NODES = {}
    _VOICE_NAMES = {}

NODE_CLASS_MAPPINGS = {**_IMAGE_NODES, **_VOICE_NODES}
NODE_DISPLAY_NAME_MAPPINGS = {**_IMAGE_NAMES, **_VOICE_NAMES}
