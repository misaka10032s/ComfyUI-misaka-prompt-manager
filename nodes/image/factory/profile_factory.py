import os
import json
import folder_paths
from ._shared import apply_assets, get_storage_path, process_output_name


class MisakaImageProfileFactory:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "checkpoint": (folder_paths.get_filename_list("checkpoints"), ),
                "character": ("STRING", {"multiline": True, "default": "", "rows": 3}),
                "H": ("STRING", {"multiline": True, "default": "", "rows": 3}),
                "expression": ("STRING", {"multiline": True, "default": "", "rows": 3}),
                "pose": ("STRING", {"multiline": True, "default": "", "rows": 3}),
                "scene": ("STRING", {"multiline": True, "default": "", "rows": 3}),
                "output_name": ("STRING", {"default": "CharacterName/Action"}),
                "save_as_profile": ("STRING", {"default": ""}),
                "clip_skip": ("INT", {"default": 0, "min": -24, "max": 0, "step": 1}),
            },
            "optional": {
                "lora_1": (["None"] + folder_paths.get_filename_list("loras"), ),
                "l1_strength_model": ("FLOAT", {"default": 1.0, "min": -10.0, "max": 10.0, "step": 0.01}),
                "l1_strength_clip": ("FLOAT", {"default": 1.0, "min": -10.0, "max": 10.0, "step": 0.01}),
                "node_map": ("STRING", {"default": "{}", "multiline": False}),
                "lora_data": ("STRING", {"default": "[]", "multiline": False}),
            },
            "hidden": {"prompt": "PROMPT", "extra_pnginfo": "EXTRA_PNGINFO"},
        }

    RETURN_TYPES = ("MODEL", "CLIP", "VAE", "CONDITIONING", "STRING")
    RETURN_NAMES = ("MODEL", "CLIP", "VAE", "POSITIVE", "formatted_name")
    FUNCTION = "execute"
    CATEGORY = "MisakaNodes/Image"

    def execute(self, checkpoint, character, H, expression, pose, scene,
                output_name, save_as_profile, clip_skip, seed=0,
                prompt=None, extra_pnginfo=None, node_map=None, lora_data=None, **kwargs):
        final_loras = []

        if lora_data and lora_data.strip() and lora_data != "[]":
            try:
                final_loras = json.loads(lora_data)
                final_loras = [l for l in final_loras if l.get("name") and l.get("name") != "None"]
            except Exception as e:
                print(f"[Misaka] Error parsing lora_data: {e}")

        if not final_loras:
            l1_name = kwargs.get("lora_1")
            if l1_name and l1_name != "None":
                final_loras.append({
                    "name": l1_name,
                    "strength_model": float(kwargs.get("l1_strength_model", 1.0)),
                    "strength_clip": float(kwargs.get("l1_strength_clip", 1.0)),
                })

        negative_text = ""
        prompt_dict = {
            "character": character,
            "H": H,
            "expression": expression,
            "pose": pose,
            "scene": scene,
        }

        if save_as_profile and save_as_profile.strip():
            base_path = get_storage_path()
            if checkpoint and not base_path.strip().startswith("/"):
                model_stem = os.path.splitext(os.path.basename(checkpoint))[0]
                base_path = f"{base_path}/{model_stem}"

            save_path = os.path.join(base_path, save_as_profile.strip() + ".json")

            note_content = ""
            if extra_pnginfo and "workflow" in extra_pnginfo:
                for n in extra_pnginfo["workflow"].get("nodes", []):
                    if n.get("type") == "CLIPTextEncode" and n.get("title") == "note":
                        vals = n.get("widgets_values")
                        if vals and len(vals) > 0:
                            note_content = str(vals[0])
                        break

            try:
                os.makedirs(os.path.dirname(save_path), exist_ok=True)
                data = {
                    "checkpoint": checkpoint,
                    "loras": final_loras,
                    "character": character,
                    "H": H,
                    "expression": expression,
                    "pose": pose,
                    "scene": scene,
                    "negative": negative_text,
                    "output_name": output_name,
                    "clip_skip": clip_skip,
                    "note": note_content,
                }
                with open(save_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=4, ensure_ascii=False)
                print(f"[Misaka] Profile saved to: {save_path}")
            except Exception as e:
                print(f"[Misaka] Error saving profile: {e}")

        model, clip, vae, pos, neg = apply_assets(checkpoint, final_loras, prompt_dict, negative_text, clip_skip)
        final_output_name = process_output_name(output_name, prompt, extra_pnginfo, node_map, checkpoint)
        return (model, clip, vae, pos, final_output_name)
