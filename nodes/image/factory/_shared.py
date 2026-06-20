import os
import json
import re
import torch
import folder_paths
import comfy.sd
import comfy.utils


def encode_prompts(clip, prompt_input):
    tokens_list = []

    if isinstance(prompt_input, str):
        if prompt_input.strip():
            tokens_list.append(prompt_input)
    elif isinstance(prompt_input, dict):
        order = ["character", "H", "expression", "pose", "scene"]
        for key in order:
            val = prompt_input.get(key, "")
            if val and val.strip():
                tokens_list.append(val)
        if "positive" in prompt_input and prompt_input["positive"].strip():
            tokens_list.insert(0, prompt_input["positive"])

    if not tokens_list:
        tokens_list.append("")

    final_cond = None

    for text in tokens_list:
        tokens = clip.tokenize(text)
        cond, pooled = clip.encode_from_tokens(tokens, return_pooled=True)
        current_cond = [[cond, {"pooled_output": pooled}]]

        if final_cond is None:
            final_cond = current_cond
        else:
            out = []
            c_to = final_cond[0]
            c_from = current_cond[0]
            if c_to[0].shape[0] == c_from[0].shape[0]:
                new_tensor = torch.cat((c_to[0], c_from[0]), 1)
                new_dict = c_to[1].copy()
                out.append([new_tensor, new_dict])
            final_cond = out

    return final_cond


def apply_assets(ckpt_name, loras_list, pos_input, neg_text="", clip_skip=0):
    ckpt_path = folder_paths.get_full_path("checkpoints", ckpt_name)
    if not ckpt_path:
        raise ValueError(f"Checkpoint '{ckpt_name}' not found")

    out = comfy.sd.load_checkpoint_guess_config(
        ckpt_path, output_vae=True, output_clip=True,
        embedding_directory=folder_paths.get_folder_paths("embeddings")
    )
    model, clip, vae = out[:3]

    for lora in loras_list:
        l_name = lora.get("name")
        if not l_name or l_name == "None":
            continue
        l_str_model = float(lora.get("strength_model", 1.0))
        l_str_clip = float(lora.get("strength_clip", 1.0))
        l_path = folder_paths.get_full_path("loras", l_name)
        if not l_path:
            print(f"Warning: LoRA '{l_name}' not found, skipping.")
            continue
        lora_weights = comfy.utils.load_torch_file(l_path, safe_load=True)
        model, clip = comfy.sd.load_lora_for_models(model, clip, lora_weights, l_str_model, l_str_clip)

    if clip_skip < 0:
        clip = clip.clone()
        clip.clip_layer(clip_skip)

    positive = encode_prompts(clip, pos_input)

    tokens_neg = clip.tokenize(neg_text)
    cond_neg, pooled_neg = clip.encode_from_tokens(tokens_neg, return_pooled=True)
    negative = [[cond_neg, {"pooled_output": pooled_neg}]]

    return model, clip, vae, positive, negative


def get_storage_path():
    base = os.path.dirname(os.path.abspath(__file__))
    # Walk up: _shared.py → factory/ → image/ → nodes/ → plugin root
    plugin_root = os.path.dirname(os.path.dirname(os.path.dirname(base)))
    return os.path.abspath(os.path.join(plugin_root, "../../user/default/misaka-prompt-sets"))


# Path-traversal-safe resolver lives in a dep-free module so it stays unit-testable.
from ._paths import resolve_profile_path  # noqa: F401  (re-exported)


def process_output_name(name_template, prompt=None, extra_pnginfo=None, node_map_str=None, checkpoint_name=None):
    if not name_template:
        return "ComfyUI"

    if checkpoint_name and not name_template.strip().startswith("/"):
        base_name = os.path.basename(checkpoint_name)
        model_stem = os.path.splitext(base_name)[0]
        name_template = f"{model_stem}/{name_template}"

    name_template = f"images/{name_template}"

    node_map = {}
    if node_map_str and isinstance(node_map_str, str):
        try:
            node_map = json.loads(node_map_str)
        except Exception:
            pass

    pattern = re.compile(r"%([^%]+)%")

    def replacer(match):
        content = match.group(1)
        if '.' not in content:
            return match.group(0)

        target_node, target_field = content.rsplit('.', 1)
        target_node_lower = target_node.lower()
        target_field_lower = target_field.lower()

        target_node_id = None
        for title, nid in node_map.items():
            if title.lower() == target_node_lower:
                target_node_id = str(nid)
                break

        if not target_node_id and target_node.isdigit():
            target_node_id = target_node

        if not prompt:
            return match.group(0)

        for node_id, node_data in prompt.items():
            current_id_str = str(node_id)
            class_type = node_data.get("class_type", "").lower()
            inputs = node_data.get("inputs", {})

            match_found = False
            if target_node_id and current_id_str == target_node_id:
                match_found = True
            elif not target_node_id and target_node_lower == class_type:
                match_found = True

            if match_found:
                found_val = None
                if target_field in inputs:
                    found_val = inputs[target_field]
                elif target_field_lower in inputs:
                    found_val = inputs[target_field_lower]
                elif "seed" in target_field_lower:
                    if "noise_seed" in inputs:
                        found_val = inputs["noise_seed"]
                    elif "seed" in inputs:
                        found_val = inputs["seed"]

                if found_val is not None:
                    if isinstance(found_val, list):
                        return match.group(0)
                    return str(found_val)

        return match.group(0)

    return pattern.sub(replacer, name_template)
