import re
import threading


class _LoopState:
    """
    Module-level singleton shared by MisakaLoopCkptCore and MisakaLoopPromptCore.

    Supports multiple PromptCore nodes via the 'dimension' parameter.
    Total runs = N_ckpts × dim_sizes[1] × dim_sizes[2] × ...
    Ordering (outermost→innermost): ckpt → dim1 → dim2 → ... → dimN
    (higher dimension number = faster cycling).

    dim_sizes  populated by each PromptCore.execute() from the previous run;
               CkptCore reads them to compute indices for the CURRENT run.
               On the very first run dim_sizes is empty → all dims default to 1,
               so the first queue always lands on index 0 for every dimension.
               Subsequent queues use the correct sizes registered by the previous run.
    """
    run_index   = 0
    current_run = 0
    # written by CkptCore, read by PromptCore
    n_ckpts     = 1
    ckpt_idx    = 0
    ckpt_stem   = "output"
    ckpt_ran    = False    # set True by CkptCore; never cleared (PromptCore just reads it)
    # multi-dim support
    dim_sizes      = {}    # {dimension: M} — "committed": CkptCore reads this each run
    dim_sizes_next = {}    # {dimension: M} — PromptCore writes here; promoted at next CkptCore run
    dim_indices    = {}    # {dimension: idx} — computed by CkptCore.execute
    dim_alias_list = {}    # {dimension: [alias0, alias1, ...]} — written directly by PromptCore each run
    # solo mode (no CkptCore): per-dimension counter
    solo_indices   = {}    # {dimension: idx}
    lock           = threading.Lock()


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
