import re
from ._state import _LoopState, _resolve_prompt_templates


class MisakaLoopPromptCore:
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
            raise ValueError("[MisakaLoopPromptCore] No prompt inputs connected")

        M = len(prompts)
        with _LoopState.lock:
            _LoopState.n_prompts = M
            coordinated = _LoopState.ckpt_ran
            if coordinated:
                # paired with LoopCkptCore: use current_run to stay in sync
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

        print(f"[MisakaLoopPromptCore] {run_info}")
        return ([[cond, {"pooled_output": pooled}]], formatted_name, run_info)
