import folder_paths


class MisakaLoopPrompt:
    """UI helper: wraps an (alias, text) pair as a MISAKA_PROMPT wire for MisakaLoopPromptCore."""
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
