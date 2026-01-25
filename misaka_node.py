import os
import json
import re
import torch
import folder_paths
import comfy.sd
import comfy.utils
import nodes

# 共享的加載邏輯
# Helper: Encode and Concat Prompts
def encode_prompts(clip, prompt_input):
    tokens_list = []
    
    # 1. Normalize input to list of strings
    if isinstance(prompt_input, str):
        if prompt_input.strip():
            tokens_list.append(prompt_input)
    elif isinstance(prompt_input, dict):
        # 定義串接順序
        order = ["character", "H", "expression", "pose", "scene"]
        for key in order:
            val = prompt_input.get(key, "")
            if val and val.strip():
                tokens_list.append(val)
        # 處理額外可能的 keys (例如舊的 positive)? 不，只處理定義好的
        if "positive" in prompt_input and prompt_input["positive"].strip():
             # 如果混用了舊格式，加在最前面?
             tokens_list.insert(0, prompt_input["positive"])

    if not tokens_list:
        tokens_list.append("") # Empty fallback

    # 2. Encode and Concat
    final_cond = None
    
    for text in tokens_list:
        tokens = clip.tokenize(text)
        cond, pooled = clip.encode_from_tokens(tokens, return_pooled=True)
        current_cond = [[cond, {"pooled_output": pooled}]]
        
        if final_cond is None:
            final_cond = current_cond
        else:
            # Concat Logic
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
    # 1. Load Checkpoint
    ckpt_path = folder_paths.get_full_path("checkpoints", ckpt_name)
    if not ckpt_path:
        raise ValueError(f"Checkpoint '{ckpt_name}' not found")
        
    out = comfy.sd.load_checkpoint_guess_config(ckpt_path, output_vae=True, output_clip=True, embedding_directory=folder_paths.get_folder_paths("embeddings"))
    model, clip, vae = out[:3]
    
    # 2. Load LoRAs
    for lora in loras_list:
        l_name = lora.get("name")
        if not l_name or l_name == "None": continue
        
        l_str_model = float(lora.get("strength_model", 1.0))
        l_str_clip = float(lora.get("strength_clip", 1.0))
        
        l_path = folder_paths.get_full_path("loras", l_name)
        if not l_path:
            print(f"Warning: LoRA '{l_name}' not found, skipping.")
            continue
            
        lora_weights = comfy.utils.load_torch_file(l_path, safe_load=True)
        model, clip = comfy.sd.load_lora_for_models(model, clip, lora_weights, l_str_model, l_str_clip)
    
    # 3. Apply CLIP Skip
    if clip_skip < 0: 
        clip = clip.clone()
        clip.clip_layer(clip_skip)

    # 4. Encode Prompts (Multi-part support)
    positive = encode_prompts(clip, pos_input)
    
    # Negative 預設為空
    tokens_neg = clip.tokenize(neg_text)
    cond_neg, pooled_neg = clip.encode_from_tokens(tokens_neg, return_pooled=True)
    negative = [[cond_neg, {"pooled_output": pooled_neg}]]
    
    return model, clip, vae, positive, negative

def get_storage_path():
    base = os.path.dirname(__file__)
    target = os.path.abspath(os.path.join(base, "../../user/default/misaka-prompt-sets"))
    return target

# 使用 prompt (execution data) 處理檔名
def process_output_name(name_template, prompt=None, extra_pnginfo=None, node_map_str=None, checkpoint_name=None):
    if not name_template:
        return "ComfyUI"
    
    # 處理 Model Name 前綴
    # 如果 checkpoint_name 存在且 template 不以 / 開頭
    if checkpoint_name and not name_template.strip().startswith("/"):
        # 提取檔名 (去除路徑和副檔名)
        base_name = os.path.basename(checkpoint_name)
        model_stem = os.path.splitext(base_name)[0]
        name_template = f"{model_stem}/{name_template}"
    
    # 解析 Node Map (Title -> ID)
    node_map = {}
    if node_map_str and isinstance(node_map_str, str):
        try:
            node_map = json.loads(node_map_str)
        except:
            pass

    # pattern: %NodeTitle_or_ID.InputName%
    pattern = re.compile(r"%([^%]+)%")
    
    def replacer(match):
        content = match.group(1) 
        if '.' not in content:
            return match.group(0) 
            
        target_node, target_field = content.rsplit('.', 1)
        target_node_lower = target_node.lower()
        target_field_lower = target_field.lower()

        # 尋找目標 Node ID
        target_node_id = None
        
        # 1. 嘗試從 Node Map (Title -> ID) 查找
        for title, nid in node_map.items():
            if title.lower() == target_node_lower:
                target_node_id = str(nid)
                break
        
        # 2. 如果 Map 沒找到，假設它是 ID
        if not target_node_id and target_node.isdigit():
            target_node_id = target_node
        
        if not prompt:
             return match.group(0)

        # 遍歷 prompt 尋找數值
        for node_id, node_data in prompt.items():
            current_id_str = str(node_id)
            class_type = node_data.get("class_type", "").lower()
            inputs = node_data.get("inputs", {})
            
            match_found = False
            
            # A. ID 匹配
            if target_node_id and current_id_str == target_node_id:
                match_found = True
            
            # B. Class Type 匹配 (只有當沒指定 ID 或 ID 沒對上時)
            elif not target_node_id and target_node_lower == class_type:
                match_found = True
                
            if match_found:
                # 嘗試在 inputs 中尋找欄位 (Case Insensitive)
                found_val = None
                
                # 直接比對
                if target_field in inputs: found_val = inputs[target_field]
                elif target_field_lower in inputs: found_val = inputs[target_field_lower]
                
                # 特例：Seed
                elif "seed" in target_field_lower:
                    if "noise_seed" in inputs: found_val = inputs["noise_seed"]
                    elif "seed" in inputs: found_val = inputs["seed"]
                
                if found_val is not None:
                    if isinstance(found_val, list):
                        return match.group(0)
                    return str(found_val)

        return match.group(0)

    return pattern.sub(replacer, name_template)

class MisakaProfileFactory:
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
                "note": ("STRING", {"multiline": True, "default": "", "rows": 3}),
            },
            "hidden": {"prompt": "PROMPT", "extra_pnginfo": "EXTRA_PNGINFO"},
        }

    RETURN_TYPES = ("MODEL", "CLIP", "VAE", "CONDITIONING", "STRING")
    RETURN_NAMES = ("MODEL", "CLIP", "VAE", "POSITIVE", "formatted_name")
    FUNCTION = "execute"
    CATEGORY = "MisakaNodes"

    def execute(self, checkpoint, character, H, expression, pose, scene, output_name, save_as_profile, clip_skip, seed=0, prompt=None, extra_pnginfo=None, node_map=None, lora_data=None, note="", **kwargs):
        final_loras = []
        
        # 1. Parse Loras
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
                    "strength_clip": float(kwargs.get("l1_strength_clip", 1.0))
                })

        negative_text = "" 
        
        # Gather prompts
        prompt_dict = {
            "character": character,
            "H": H,
            "expression": expression,
            "pose": pose,
            "scene": scene
        }

        if save_as_profile and save_as_profile.strip():
            base_path = get_storage_path()
            save_path = os.path.join(base_path, save_as_profile.strip() + ".json")
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
                    "note": note
                }
                with open(save_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=4, ensure_ascii=False)
                print(f"[Misaka] Profile saved to: {save_path}")
            except Exception as e:
                print(f"[Misaka] Error saving profile: {e}")

        model, clip, vae, pos, neg = apply_assets(checkpoint, final_loras, prompt_dict, negative_text, clip_skip)
        
        final_output_name = process_output_name(output_name, prompt, extra_pnginfo, node_map, checkpoint)
        
        return (model, clip, vae, pos, final_output_name)

class MisakaPromptManager:
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
    CATEGORY = "MisakaNodes"

    def load(self, profile, prompt=None, extra_pnginfo=None, node_map=None):
        if profile == "None": raise ValueError("Select a profile")
        
        base = get_storage_path()
        with open(os.path.join(base, profile + ".json"), 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        # 嘗試讀取新版欄位
        prompt_input = {}
        new_keys = ["character", "H", "expression", "pose", "scene"]
        has_new = False
        for k in new_keys:
            if k in data:
                prompt_input[k] = data[k]
                has_new = True
        
        # 如果沒有新版欄位，使用舊版 positive
        if not has_new:
            prompt_input = data.get("positive", "")
            
        model, clip, vae, pos, neg = apply_assets(
            data["checkpoint"], 
            data.get("loras", []), 
            prompt_input, 
            data.get("negative", ""),
            data.get("clip_skip", 0) # 從存檔讀取，預設 0 (Auto)
        )
        
        raw_name = data.get("output_name", "ComfyUI")
        # 在 Manager 這裡才進行 %Seed.seed% 的轉換並輸出
        final_output_name = process_output_name(raw_name, prompt, extra_pnginfo, node_map, data["checkpoint"])
        
        return (model, clip, vae, pos, final_output_name)

class MisakaPromptBuilder:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "clip": ("CLIP", ),
                "text_1": ("STRING", {"multiline": True, "default": "", "rows": 6}),
            },
            "optional": {
                "conditioning_in": ("CONDITIONING", ),
                "prompt_data": ("STRING", {"default": "[]", "multiline": False}),
            }
        }

    RETURN_TYPES = ("CONDITIONING", )
    RETURN_NAMES = ("CONDITIONING", )
    FUNCTION = "execute"
    CATEGORY = "MisakaNodes"

    def execute(self, clip, text_1, conditioning_in=None, prompt_data=None, **kwargs):
        import torch
        
        # Helper for encoding text
        def encode_text(text):
            tokens = clip.tokenize(text)
            cond, pooled = clip.encode_from_tokens(tokens, return_pooled=True)
            return [[cond, {"pooled_output": pooled}]]

        # Helper for concatenating conditioning (to + from)
        def concat_cond(c_to, c_from):
            out = []
            if len(c_to) > 1:
                print("[Misaka] Warning: Batch conditioning concat not fully supported, using first.")
            
            t_to = c_to[0]
            t_from = c_from[0]
            
            tensor_to = t_to[0]
            tensor_from = t_from[0]
            
            if tensor_to.shape[0] == tensor_from.shape[0]:
                new_tensor = torch.cat((tensor_to, tensor_from), 1)
                new_dict = t_to[1].copy()
                out.append([new_tensor, new_dict])
            return out

        # 1. Determine Initial Conditioning
        final_conditioning = None
        
        if conditioning_in is not None:
            final_conditioning = conditioning_in
        
        if text_1 and text_1.strip():
            cond_1 = encode_text(text_1)
            if final_conditioning is None:
                final_conditioning = cond_1
            else:
                final_conditioning = concat_cond(final_conditioning, cond_1)
        
        # Fallback
        if final_conditioning is None:
             final_conditioning = encode_text("")

        # 2. Iterate dynamically added texts (via prompt_data JSON)
        extra_texts = []
        if prompt_data and isinstance(prompt_data, str):
            try:
                extra_texts = json.loads(prompt_data)
            except:
                pass
        
        for text_val in extra_texts:
            if text_val and text_val.strip():
                cond_next = encode_text(text_val)
                final_conditioning = concat_cond(final_conditioning, cond_next)
            
        return (final_conditioning, )
NODE_CLASS_MAPPINGS = {
    "MisakaProfileFactory": MisakaProfileFactory,
    "MisakaPromptManager": MisakaPromptManager,
    "MisakaPromptBuilder": MisakaPromptBuilder
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MisakaProfileFactory": "Misaka Profile Factory (Editor/Saver)",
    "MisakaPromptManager": "Misaka Prompt Manager (Loader)",
    "MisakaPromptBuilder": "Misaka Prompt Builder (Multi-Concat)"
}
