import json
import torch


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
