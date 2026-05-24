import os
import json
import folder_paths
from ._shared import apply_assets, get_storage_path, process_output_name


class MisakaImagePromptManager:
    @classmethod
    def INPUT_TYPES(s):
        base = get_storage_path()
        profiles = ["None"]
        if os.path.exists(base):
            for root, dirs, files in os.walk(base):
                for file in files:
                    if file.endswith(".json"):
                        rel = os.path.relpath(os.path.join(root, file), base)
                        profiles.append(os.path.splitext(rel)[0].replace("\\", "/"))

        return {
            "required": {"profile": (sorted(profiles), )},
            "optional": {
                "node_map": ("STRING", {"default": "{}", "multiline": False}),
            },
            "hidden": {"prompt": "PROMPT", "extra_pnginfo": "EXTRA_PNGINFO"},
        }

    RETURN_TYPES = ("MODEL", "CLIP", "VAE", "CONDITIONING", "STRING")
    RETURN_NAMES = ("MODEL", "CLIP", "VAE", "POSITIVE", "output_name")
    FUNCTION = "load"
    CATEGORY = "MisakaNodes/Image"

    def load(self, profile, prompt=None, extra_pnginfo=None, node_map=None):
        if profile == "None":
            raise ValueError("Select a profile")

        base = get_storage_path()
        with open(os.path.join(base, profile + ".json"), 'r', encoding='utf-8') as f:
            data = json.load(f)

        prompt_input = {}
        new_keys = ["character", "H", "expression", "pose", "scene"]
        has_new = any(k in data for k in new_keys)

        if has_new:
            for k in new_keys:
                if k in data:
                    prompt_input[k] = data[k]
        else:
            prompt_input = data.get("positive", "")

        model, clip, vae, pos, neg = apply_assets(
            data["checkpoint"],
            data.get("loras", []),
            prompt_input,
            data.get("negative", ""),
            data.get("clip_skip", 0),
        )

        raw_name = data.get("output_name", "ComfyUI")
        final_output_name = process_output_name(raw_name, prompt, extra_pnginfo, node_map, data["checkpoint"])
        return (model, clip, vae, pos, final_output_name)
