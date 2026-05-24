import os
import re
import folder_paths
import comfy.sd
from ._state import _LoopState, _resolve_prompt_templates


class MisakaLoopCkptCore:
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
            raise ValueError("[MisakaLoopCkptCore] No checkpoint names connected")

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
            # share ckpt info for LoopPromptCore
            _LoopState.n_ckpts   = N
            _LoopState.ckpt_idx  = ckpt_idx
            _LoopState.ckpt_ran  = True

        name = names[ckpt_idx]
        ckpt_path = folder_paths.get_full_path("checkpoints", name)
        if not ckpt_path:
            raise ValueError(f"[MisakaLoopCkptCore] Checkpoint '{name}' not found")

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
        print(f"[MisakaLoopCkptCore] {run_info}  (run {run + 1}/{total})")
        return (model, clip, vae, formatted_name, run_info)
