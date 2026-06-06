import re
from ._state import _LoopState


class MisakaLoopPromptCore:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "clip": ("CLIP",),
            },
            "optional": {
                "prompt_1": ("MISAKA_PROMPT",),
            },
            "hidden": {
                "unique_id": "UNIQUE_ID",
            },
        }

    RETURN_TYPES = ("CONDITIONING",)
    RETURN_NAMES = ("CONDITIONING",)
    FUNCTION = "execute"
    CATEGORY = "MisakaNodes/Image"

    @classmethod
    def IS_CHANGED(cls, clip, **kwargs):
        return float("nan")

    @classmethod
    def VALIDATE_INPUTS(cls, **kwargs):
        return True

    def execute(self, clip, unique_id=None, **kwargs):
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
        all_aliases = [a for a, _ in prompts]
        node_key = str(unique_id) if unique_id is not None else "default"

        with _LoopState.lock:
            # Register our size for the NEXT CkptCore run (pending/committed swap pattern)
            _LoopState.dim_sizes_next[node_key] = M
            # Write alias list directly so PathManager can read it this run
            _LoopState.dim_alias_list[node_key] = all_aliases

            if _LoopState.ckpt_ran:
                idx = _LoopState.dim_indices.get(node_key, _LoopState.current_run % M)
            else:
                prev = _LoopState.solo_indices.get(node_key, 0)
                idx  = prev % M
                _LoopState.solo_indices[node_key] = (idx + 1) % M

        alias, text = prompts[idx]
        tokens = clip.tokenize(text)
        cond, pooled = clip.encode_from_tokens(tokens, return_pooled=True)

        print(f"[MisakaLoopPromptCore] node={node_key} {idx + 1}/{M}: {alias}")
        return ([[cond, {"pooled_output": pooled}]],)


