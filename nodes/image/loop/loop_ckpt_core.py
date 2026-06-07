import os
import re
import folder_paths
import comfy.sd
from ._state import _LoopState


class MisakaLoopCkptCore:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {},
            "optional": {
                "ckpt_name_1": ("STRING", {"forceInput": True}),
            },
        }

    RETURN_TYPES = ("MODEL", "CLIP", "VAE")
    RETURN_NAMES = ("MODEL", "CLIP", "VAE")
    FUNCTION = "execute"
    CATEGORY = "MisakaNodes/Image"

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    @classmethod
    def VALIDATE_INPUTS(cls, **kwargs):
        return True

    def execute(self, **kwargs):
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
            # Promote pending dim_sizes (registered by PromptCore in the previous run).
            # This ensures stale entries from removed PromptCore nodes don't linger.
            if _LoopState.dim_sizes_next:
                _LoopState.dim_sizes = dict(_LoopState.dim_sizes_next)
                _LoopState.dim_sizes_next = {}

            # Compute total runs across all registered prompt dimensions.
            # On the very first run dim_sizes is empty → dim_product defaults to 1.
            dim_sizes = dict(_LoopState.dim_sizes)
            dim_product = 1
            for size in dim_sizes.values():
                dim_product *= max(size, 1)

            total    = N * dim_product
            run      = _LoopState.run_index % total
            _LoopState.current_run = run
            _LoopState.run_index   = (run + 1) % total

            # Ckpt is the outermost (slowest) dimension
            ckpt_idx = (run // dim_product) % N

            # Compute per-prompt-dimension indices (odometer: dim1 slowest, dimN fastest)
            sorted_dims = sorted(dim_sizes.keys())
            remaining   = run % dim_product
            dim_indices = {}
            for dim in reversed(sorted_dims):
                size = max(dim_sizes[dim], 1)
                dim_indices[dim] = remaining % size
                remaining //= size

            _LoopState.n_ckpts     = N
            _LoopState.ckpt_idx    = ckpt_idx
            _LoopState.ckpt_ran    = True
            _LoopState.dim_indices = dim_indices

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

        print(f"[MisakaLoopCkptCore] ckpt {ckpt_idx + 1}/{N}: {ckpt_stem}  run {run + 1}/{total}")
        return (model, clip, vae)

