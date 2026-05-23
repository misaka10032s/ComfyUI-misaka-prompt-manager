import os
import json
import re
import threading
import torch
import folder_paths
import comfy.sd
import comfy.utils
import nodes


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
    base = os.path.dirname(__file__)
    return os.path.abspath(os.path.join(base, "../../user/default/misaka-prompt-sets"))


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


class MisakaImagePromptBuilder:
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
            },
        }

    RETURN_TYPES = ("CONDITIONING", )
    RETURN_NAMES = ("CONDITIONING", )
    FUNCTION = "execute"
    CATEGORY = "MisakaNodes/Image"

    def execute(self, clip, text_1, conditioning_in=None, prompt_data=None, **kwargs):
        def encode_text(text):
            tokens = clip.tokenize(text)
            cond, pooled = clip.encode_from_tokens(tokens, return_pooled=True)
            return [[cond, {"pooled_output": pooled}]]

        def concat_cond(c_to, c_from):
            if len(c_to) > 1:
                print("[Misaka] Warning: Batch conditioning concat not fully supported, using first.")
            t_to = c_to[0]
            t_from = c_from[0]
            if t_to[0].shape[0] == t_from[0].shape[0]:
                new_tensor = torch.cat((t_to[0], t_from[0]), 1)
                return [[new_tensor, t_to[1].copy()]]
            return c_to

        final_conditioning = conditioning_in

        if text_1 and text_1.strip():
            cond_1 = encode_text(text_1)
            if final_conditioning is None:
                final_conditioning = cond_1
            else:
                final_conditioning = concat_cond(final_conditioning, cond_1)

        if final_conditioning is None:
            final_conditioning = encode_text("")

        extra_texts = []
        if prompt_data and isinstance(prompt_data, str):
            try:
                extra_texts = json.loads(prompt_data)
            except Exception:
                pass

        for text_val in extra_texts:
            if text_val and text_val.strip():
                final_conditioning = concat_cond(final_conditioning, encode_text(text_val))

        return (final_conditioning, )


# ---------------------------------------------------------------------------
# Scale / Size helpers
# ---------------------------------------------------------------------------

_SCALE_PRESETS = [
    # ── SD 1.5 (~512K px) ───────────────────────────────────────────────────
    "512×512  (1:1)",
    "512×768  (2:3)",
    "768×512  (3:2)",
    "512×640  (4:5)",
    "640×512  (5:4)",
    "512×682  (3:4)",
    "682×512  (4:3)",
    "576×1024 (9:16)",
    "1024×576 (16:9)",
    # ── SDXL / Pony (~1M px) ────────────────────────────────────────────────
    "1024×1024 (1:1  XL)",
    "832×1216  (2:3  XL)",
    "1216×832  (3:2  XL)",
    "896×1152  (7:9  XL)",
    "1152×896  (9:7  XL)",
    "768×1344  (4:7  XL)",
    "1344×768  (7:4  XL)",
    "640×1536  (5:12 XL)",
    "1536×640  (12:5 XL)",
]

_ASPECT_RATIOS = [
    "free",
    "1:1",
    "2:3",
    "3:2",
    "3:4",
    "4:3",
    "9:16",
    "16:9",
    "4:5",
    "5:4",
    "7:9",
    "9:7",
    "2:1",
    "1:2",
]


def _round8(v: float) -> int:
    return max(8, round(v / 8) * 8)


def _parse_preset(s: str):
    m = re.search(r"(\d+)[×x](\d+)", s)
    return int(m.group(1)), int(m.group(2))


class MisakaScalePreset:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "preset": (_SCALE_PRESETS, {"default": _SCALE_PRESETS[1]}),
                "scale": ("FLOAT", {"default": 1.5, "min": 1.0, "max": 8.0, "step": 0.25}),
            },
        }

    RETURN_TYPES = ("INT", "INT", "INT", "INT", "STRING")
    RETURN_NAMES = ("width", "height", "scaled_width", "scaled_height", "info")
    FUNCTION = "execute"
    CATEGORY = "MisakaNodes"

    def execute(self, preset, scale):
        w, h = _parse_preset(preset)
        sw, sh = _round8(w * scale), _round8(h * scale)
        info = f"{w}×{h}  →  {sw}×{sh}  ({scale:.2f}×)"
        return (w, h, sw, sh, info)


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


class MisakaPromptText:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "alias": ("STRING", {"default": "alias", "multiline": False}),
                "text":  ("STRING", {"default": "", "multiline": True, "rows": 6}),
            }
        }

    RETURN_TYPES = ("MISAKA_PROMPT",)
    RETURN_NAMES = ("prompt",)
    FUNCTION = "execute"
    CATEGORY = "MisakaNodes/Image"

    def execute(self, alias, text):
        return ((alias.strip(), text.strip()),)


class MisakaCkptName:
    """UI-only helper: exposes a checkpoint dropdown and passes the selected name as a STRING wire."""
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {"ckpt_name": (folder_paths.get_filename_list("checkpoints"),)}}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("ckpt_name",)
    FUNCTION = "execute"
    CATEGORY = "MisakaNodes/Image"

    def execute(self, ckpt_name):
        return (ckpt_name,)


class _LoopState:
    """
    Module-level singleton shared by MisakaLoopCkpt and MisakaLoopPrompt.

    LIMITATION: only one LoopCkpt+LoopPrompt pair per workflow is supported.
    Placing two separate pairs in the same graph will cause them to share this
    state and interfere with each other's counters.
    """
    run_index        = 0
    current_run      = 0
    n_prompts        = 1
    # written by LoopCkpt, read by LoopPrompt
    n_ckpts          = 1
    ckpt_idx         = 0
    ckpt_stem        = "output"
    ckpt_ran         = False   # True while LoopPrompt hasn't yet consumed this run's ckpt info
    # independent counter for solo LoopPrompt (no LoopCkpt in the workflow)
    prompt_solo_index = 0
    lock             = threading.Lock()


class MisakaLoopCkpt:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "reset_counter": ("BOOLEAN", {
                    "default": False,
                    "label_on": "Reset (next run restarts from run 1)",
                    "label_off": "Continue",
                }),
            },
            "optional": {
                "ckpt_name_1": ("STRING", {"forceInput": True}),
                "base_folder":  ("STRING", {"default": "images/test", "multiline": False}),
            },
            "hidden": {
                "prompt": "PROMPT",
            },
        }

    RETURN_TYPES = ("MODEL", "CLIP", "VAE", "STRING", "STRING")
    RETURN_NAMES = ("MODEL", "CLIP", "VAE", "formatted_name", "run_info")
    FUNCTION = "execute"
    CATEGORY = "MisakaNodes/Image"

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    @classmethod
    def VALIDATE_INPUTS(cls, **kwargs):
        return True

    def execute(self, reset_counter=False, base_folder="images/test", prompt=None, **kwargs):
        # Collect all ckpt_name_N inputs, skipping gaps (disconnected optional ports are absent)
        entries = []
        for key, val in kwargs.items():
            m = re.fullmatch(r"ckpt_name_(\d+)", key)
            if m and isinstance(val, str) and val.strip():
                entries.append((int(m.group(1)), val.strip()))
        names = [v for _, v in sorted(entries)]

        if not names:
            raise ValueError("[MisakaLoopCkpt] No checkpoint names connected")

        N = len(names)
        with _LoopState.lock:
            # reset only when counter is not already at 0 — avoids freezing at run 1
            if reset_counter and _LoopState.run_index != 0:
                _LoopState.run_index = 0
            n_prompts = max(_LoopState.n_prompts, 1)
            total     = N * n_prompts
            run       = _LoopState.run_index % total
            _LoopState.current_run = run
            _LoopState.run_index   = (run + 1) % total
            ckpt_idx  = (run // n_prompts) % N
            # share ckpt info for LoopPrompt
            _LoopState.n_ckpts   = N
            _LoopState.ckpt_idx  = ckpt_idx
            _LoopState.ckpt_ran  = True

        name = names[ckpt_idx]
        ckpt_path = folder_paths.get_full_path("checkpoints", name)
        if not ckpt_path:
            raise ValueError(f"[MisakaLoopCkpt] Checkpoint '{name}' not found")

        out = comfy.sd.load_checkpoint_guess_config(
            ckpt_path, output_vae=True, output_clip=True,
            embedding_directory=folder_paths.get_folder_paths("embeddings")
        )
        model, clip, vae = out[:3]
        ckpt_stem = os.path.splitext(os.path.basename(name))[0]

        with _LoopState.lock:
            _LoopState.ckpt_stem = ckpt_stem

        resolved_base  = _resolve_prompt_templates(base_folder.strip().rstrip("/"), prompt or {})
        formatted_name = f"{resolved_base}/{ckpt_stem}"
        run_info       = f"ckpt {ckpt_idx + 1}/{N}: {ckpt_stem}"
        print(f"[MisakaLoopCkpt] {run_info}  (run {run + 1}/{total})")
        return (model, clip, vae, formatted_name, run_info)


def _resolve_prompt_templates(text: str, prompt: dict) -> str:
    """Replace %NodeTitle.field% tokens by looking up values in the prompt graph."""
    if not prompt or "%" not in text:
        return text
    def _replace(m):
        title, field = m.group(1), m.group(2)
        for node in prompt.values():
            if not isinstance(node, dict):
                continue
            node_title = node.get("_meta", {}).get("title", "")
            if node_title == title:
                val = node.get("inputs", {}).get(field)
                # skip if it's a connection reference (list) or missing
                if val is not None and not isinstance(val, list):
                    return str(val)
        return m.group(0)  # not found — keep raw text
    return re.sub(r"%([^%.]+)\.([^%]+)%", _replace, text)


class MisakaLoopPrompt:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "clip":        ("CLIP",),
                "base_folder": ("STRING", {"default": "images/test", "multiline": False}),
            },
            "optional": {
                "prompt_1": ("MISAKA_PROMPT",),
            },
            "hidden": {
                "prompt": "PROMPT",
            },
        }

    RETURN_TYPES = ("CONDITIONING", "STRING", "STRING")
    RETURN_NAMES = ("CONDITIONING", "formatted_name", "run_info")
    FUNCTION = "execute"
    CATEGORY = "MisakaNodes/Image"

    @classmethod
    def IS_CHANGED(cls, clip, base_folder, **kwargs):
        return float("nan")

    @classmethod
    def VALIDATE_INPUTS(cls, **kwargs):
        return True

    def execute(self, clip, base_folder, prompt=None, **kwargs):
        # Collect all prompt_N inputs, skipping gaps
        entries = []
        for key, val in kwargs.items():
            m = re.fullmatch(r"prompt_(\d+)", key)
            if m and isinstance(val, tuple) and len(val) == 2:
                entries.append((int(m.group(1)), val))
        prompts = [v for _, v in sorted(entries)]

        if not prompts:
            raise ValueError("[MisakaLoopPrompt] No prompt inputs connected")

        M = len(prompts)
        with _LoopState.lock:
            _LoopState.n_prompts = M
            coordinated = _LoopState.ckpt_ran
            if coordinated:
                # paired with LoopCkpt: use current_run to stay in sync
                idx      = _LoopState.current_run % M
                n_ckpts  = _LoopState.n_ckpts
                ckpt_idx = _LoopState.ckpt_idx
                ckpt_stem = _LoopState.ckpt_stem
                total    = n_ckpts * M
                run      = _LoopState.current_run
                _LoopState.ckpt_ran = False   # consumed
            else:
                # solo mode: advance own counter
                idx       = _LoopState.prompt_solo_index % M
                _LoopState.prompt_solo_index = (idx + 1) % M
                n_ckpts   = 0
                ckpt_idx  = 0
                ckpt_stem = _LoopState.ckpt_stem  # may be default "output"
                total     = M
                run       = idx

        alias, text = prompts[idx]
        tokens = clip.tokenize(text)
        cond, pooled = clip.encode_from_tokens(tokens, return_pooled=True)

        resolved_base = _resolve_prompt_templates(base_folder.strip().rstrip("/"), prompt or {})

        if coordinated:
            formatted_name = f"{resolved_base}/{ckpt_stem}/{alias}"
            run_info = (
                f"run {run + 1}/{total} | "
                f"ckpt {ckpt_idx + 1}/{n_ckpts}: {ckpt_stem} | "
                f"prompt {idx + 1}/{M}: {alias}"
            )
        else:
            formatted_name = f"{resolved_base}/{alias}"
            run_info = f"prompt {idx + 1}/{M}: {alias}"

        print(f"[MisakaLoopPrompt] {run_info}")
        return ([[cond, {"pooled_output": pooled}]], formatted_name, run_info)


NODE_CLASS_MAPPINGS = {
    "MisakaImageProfileFactory": MisakaImageProfileFactory,
    "MisakaImagePromptManager":  MisakaImagePromptManager,
    "MisakaImagePromptBuilder":  MisakaImagePromptBuilder,
    "MisakaScalePreset":         MisakaScalePreset,
    "MisakaScaleCustom":         MisakaScaleCustom,
    "MisakaPromptText":          MisakaPromptText,
    "MisakaCkptName":            MisakaCkptName,
    "MisakaLoopPrompt":          MisakaLoopPrompt,
    "MisakaLoopCkpt":            MisakaLoopCkpt,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MisakaImageProfileFactory": "Misaka Image Profile Factory (Editor/Saver)",
    "MisakaImagePromptManager":  "Misaka Image Prompt Manager (Loader)",
    "MisakaImagePromptBuilder":  "Misaka Image Prompt Builder (Multi-Concat)",
    "MisakaScalePreset":         "Misaka Scale Preset",
    "MisakaScaleCustom":         "Misaka Scale Custom",
    "MisakaPromptText":          "Misaka Prompt Text",
    "MisakaCkptName":            "Misaka Ckpt Name",
    "MisakaLoopPrompt":          "Misaka Loop Prompt",
    "MisakaLoopCkpt":            "Misaka Loop Ckpt",
}
