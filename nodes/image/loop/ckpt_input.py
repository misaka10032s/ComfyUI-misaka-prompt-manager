import folder_paths


class MisakaLoopCkpt:
    """UI helper: exposes a checkpoint dropdown and passes the selected name as a STRING wire."""
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {"ckpt_name": (folder_paths.get_filename_list("checkpoints"),)}}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("ckpt_name",)
    FUNCTION = "execute"
    CATEGORY = "MisakaNodes/Image"

    def execute(self, ckpt_name):
        return (ckpt_name,)
