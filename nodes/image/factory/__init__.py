from .profile_factory import MisakaImageProfileFactory
from .prompt_manager import MisakaImagePromptManager
from .prompt_builder import MisakaImagePromptBuilder
from ._shared import get_storage_path, resolve_profile_path  # re-export for __init__.py API routes
# Re-export for __init__.py API routes (same reason as the line above: importing through THIS
# already-baselined package path, rather than a new `.nodes.image.factory._origin_guard` import in
# the root __init__.py, avoids adding a 4th near-duplicate mypy "Cannot find implementation for
# module __main__.nodes.image.factory._origin_guard" structural-artifact finding to
# quality-gates/mypy-baseline.json — see .claude/CLAUDE.md -> "Code quality gates" for why the
# existing 3 such entries are accepted noise. Redundant `as`-aliases (rather than the bare-name
# style used one line above) mark these as an intentional re-export to ruff's F401 check, so no
# NEW baseline entry is needed for them either — unlike the two lines above, which predate this
# gate and stay as pre-existing baselined debt per the "never touch baselines for pre-existing,
# unrelated findings" rule.
from ._origin_guard import MAX_PROFILE_BODY_BYTES as MAX_PROFILE_BODY_BYTES
from ._origin_guard import BodyTooLarge as BodyTooLarge
from ._origin_guard import guard_same_origin as guard_same_origin
from ._origin_guard import read_capped_body as read_capped_body
from ._origin_guard import content_length_exceeds_cap as content_length_exceeds_cap

NODE_CLASS_MAPPINGS = {
    "MisakaImageProfileFactory": MisakaImageProfileFactory,
    "MisakaImagePromptManager":  MisakaImagePromptManager,
    "MisakaImagePromptBuilder":  MisakaImagePromptBuilder,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MisakaImageProfileFactory": "Misaka Image Profile Factory (Editor/Saver)",
    "MisakaImagePromptManager":  "Misaka Image Prompt Manager (Loader)",
    "MisakaImagePromptBuilder":  "Misaka Image Prompt Builder (Multi-Concat)",
}
