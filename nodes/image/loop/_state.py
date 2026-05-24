import re
import threading


class _LoopState:
    """
    Module-level singleton shared by MisakaLoopCkptCore and MisakaLoopPromptCore.

    LIMITATION: only one LoopCkptCore+LoopPromptCore pair per workflow is supported.
    Placing two separate pairs in the same graph will cause them to share this
    state and interfere with each other's counters.
    """
    run_index        = 0
    current_run      = 0
    n_prompts        = 1
    # written by LoopCkptCore, read by LoopPromptCore
    n_ckpts          = 1
    ckpt_idx         = 0
    ckpt_stem        = "output"
    ckpt_ran         = False   # True while LoopPromptCore hasn't yet consumed this run's ckpt info
    # independent counter for solo LoopPromptCore (no LoopCkptCore in the workflow)
    prompt_solo_index = 0
    lock             = threading.Lock()


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
