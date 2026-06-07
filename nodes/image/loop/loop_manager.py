import re
from ._state import _LoopState, _resolve_prompt_templates


class MisakaLoopManager:
    """
    Assembles the final formatted path from all active loop dimensions.

    Path format: {base_folder} / alias_prompt1 / alias_prompt2 / ... / ckpt_stem

    Connect MODEL (from CkptCore) and conditioning_N inputs (from each PromptCore) to
    guarantee correct execution order. The conditioning slot number (1, 2, ...) defines
    the order of path segments.
    """

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "base_folder": ("STRING", {"default": "images/test", "multiline": False}),
                "reset_counter": ("BOOLEAN", {
                    "default": False,
                    "label_on": "Reset (next run restarts from run 1)",
                    "label_off": "Continue",
                }),
            },
            "optional": {
                "model":          ("MODEL",),
                "conditioning_1": ("CONDITIONING",),
            },
            "hidden": {
                "unique_id": "UNIQUE_ID",
                "prompt":    "PROMPT",
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("formatted_name", "run_info")
    FUNCTION = "execute"
    CATEGORY = "MisakaNodes/Image"

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    @classmethod
    def VALIDATE_INPUTS(cls, **kwargs):
        return True

    def execute(self, base_folder, reset_counter=False, model=None, unique_id=None, prompt=None, **kwargs):
        resolved_base = _resolve_prompt_templates(base_folder.strip().rstrip("/"), prompt or {})

        # Resolve conditioning_N → source PromptCore node_id from the graph, in slot order
        slot_to_source = {}  # {slot_int: source_node_id_str}
        if unique_id and prompt:
            my_node = prompt.get(str(unique_id), {})
            for inp_name, val in my_node.get("inputs", {}).items():
                m = re.fullmatch(r"conditioning_(\d+)", inp_name)
                if m and isinstance(val, list) and len(val) >= 1:
                    slot_to_source[int(m.group(1))] = str(val[0])

        with _LoopState.lock:
            ckpt_ran       = _LoopState.ckpt_ran
            ckpt_stem      = _LoopState.ckpt_stem
            ckpt_idx       = _LoopState.ckpt_idx
            n_ckpts        = _LoopState.n_ckpts
            run            = _LoopState.current_run
            dim_indices    = dict(_LoopState.dim_indices)
            dim_alias_list = dict(_LoopState.dim_alias_list)
            dim_sizes      = dict(_LoopState.dim_sizes)
            dim_product = 1
            for size in dim_sizes.values():
                dim_product *= max(size, 1)
            total = (n_ckpts * dim_product) if ckpt_ran else max(dim_product, 1)

        # Build alias segments in conditioning slot order (1, 2, ...)
        alias_segments = []
        prompt_info_parts = []
        for slot in sorted(slot_to_source.keys()):
            nid = slot_to_source[slot]
            aliases = dim_alias_list.get(nid, [])
            i = dim_indices.get(nid, 0)
            M = dim_sizes.get(nid, len(aliases) or 1)
            al = aliases[i] if i < len(aliases) else f"idx{i + 1}"
            alias_segments.append(al)
            label = "prompt" if len(slot_to_source) == 1 else f"prompt{slot}"
            prompt_info_parts.append(f"{label} {i + 1}/{M}: {al}")

        # Assemble path: base / alias1 / alias2 / ... / [ckpt_stem]
        parts = [resolved_base] + alias_segments
        if ckpt_ran:
            parts.append(ckpt_stem)
        formatted_name = "/".join(parts)

        # Build run_info
        info_parts = []
        if ckpt_ran:
            info_parts.append(f"ckpt {ckpt_idx + 1}/{n_ckpts}")
        info_parts.extend(prompt_info_parts)
        info_parts.append(f"run {run + 1}/{total}")
        run_info = "  ".join(info_parts) + f"\npath: {formatted_name}"

        print(f"[MisakaLoopManager] {run_info}")

        if reset_counter:
            with _LoopState.lock:
                _LoopState.run_index = 0

        return (formatted_name, run_info)

