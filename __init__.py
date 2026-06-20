import importlib
import subprocess
import sys

# ── Auto-install missing voice dependencies at ComfyUI startup ──────────────
# Only the core audio pipeline is auto-installed (always needed for voice nodes).
# Optional RVC packages (pyworld, torchcrepe, faiss) are listed in
# requirements.txt but NOT auto-installed — they may need native build tools.
_AUTO_INSTALL = [
    ("librosa",   "librosa>=0.10.0"),      # segmentation, auto_params
    ("soundfile", "soundfile>=0.12.1"),    # resampler, batch convert, audio info
    ("soxr",      "soxr>=0.3.7"),          # resampler (HQ, no aliasing)
    ("scipy",     "scipy>=1.11.0"),        # rvc_wrapper F0 medfilt
]

def _ensure_packages():
    missing = [spec for mod, spec in _AUTO_INSTALL
               if importlib.util.find_spec(mod) is None]
    if not missing:
        return
    print(f"[Misaka] Installing missing voice dependencies: {missing}")
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--quiet"] + missing
        )
        print("[Misaka] Installation complete.")
    except Exception as e:
        print(f"[Misaka] Auto-install failed: {e}\n"
              f"         Run manually: pip install {' '.join(missing)}")

_ensure_packages()
# ─────────────────────────────────────────────────────────────────────────────

from .nodes.image import NODE_CLASS_MAPPINGS as _IMAGE_NODES
from .nodes.image import NODE_DISPLAY_NAME_MAPPINGS as _IMAGE_NAMES
from .nodes.image.factory import get_storage_path, resolve_profile_path

try:
    from .nodes.voice import NODE_CLASS_MAPPINGS as _VOICE_NODES
    from .nodes.voice import NODE_DISPLAY_NAME_MAPPINGS as _VOICE_NAMES
except Exception as e:
    print(f"[MisakaVC] Could not load voice nodes: {e}")
    _VOICE_NODES = {}
    _VOICE_NAMES = {}

NODE_CLASS_MAPPINGS = {**_IMAGE_NODES, **_VOICE_NODES}
NODE_DISPLAY_NAME_MAPPINGS = {**_IMAGE_NAMES, **_VOICE_NAMES}

from server import PromptServer
from aiohttp import web
import os
import json


@PromptServer.instance.routes.get("/misaka/profile_list")
async def get_profile_list(request):
    base = get_storage_path()
    files = []
    if os.path.exists(base):
        for root, dirs, filenames in os.walk(base):
            for f in filenames:
                if f.endswith(".json"):
                    full_path = os.path.join(root, f)
                    rel_path = os.path.relpath(full_path, base)
                    files.append(os.path.splitext(rel_path)[0].replace("\\", "/"))
    return web.json_response(sorted(files))


@PromptServer.instance.routes.get("/misaka/load_profile")
async def load_profile(request):
    name = request.query.get("name")
    if not name:
        return web.Response(status=400)

    base = get_storage_path()
    try:
        path = resolve_profile_path(base, name)
    except ValueError:
        return web.Response(status=400, text="Invalid profile name")
    if not os.path.exists(path):
        return web.Response(status=404)

    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return web.json_response(data)
    except Exception as e:
        return web.Response(status=500, text=str(e))


@PromptServer.instance.routes.post("/misaka/save_profile")
async def save_profile(request):
    try:
        data = await request.json()
        filename = data.get("filename")
        profile_data = data.get("data")

        if not filename or not profile_data:
            return web.Response(status=400, text="Missing filename or data")

        base = get_storage_path()

        if filename.startswith("/") or filename.startswith("\\"):
            relative_save_path = filename.lstrip("/").lstrip("\\")
        else:
            ckpt_name = profile_data.get("checkpoint", "")
            if ckpt_name:
                model_stem = os.path.splitext(os.path.basename(ckpt_name))[0]
                relative_save_path = os.path.join(model_stem, filename)
            else:
                relative_save_path = filename

        try:
            save_path = resolve_profile_path(base, relative_save_path)
        except ValueError:
            return web.Response(status=400, text="Invalid filename")
        os.makedirs(os.path.dirname(save_path), exist_ok=True)

        with open(save_path, 'w', encoding='utf-8') as f:
            json.dump(profile_data, f, indent=4, ensure_ascii=False)

        return web.Response(status=200, text="Saved successfully")
    except Exception as e:
        return web.Response(status=500, text=str(e))


def _scan_files(ext: str) -> list:
    """Recursively find files with given extension in common RVC model locations."""
    import folder_paths
    results = []
    search_dirs = [
        os.path.join(folder_paths.models_dir, "rvc"),
        os.path.join(folder_paths.models_dir, "RVC"),
        folder_paths.input_directory,
    ]
    for d in search_dirs:
        if os.path.isdir(d):
            for root, dirs, files in os.walk(d):
                for f in files:
                    if f.lower().endswith(ext):
                        results.append(os.path.join(root, f).replace("\\", "/"))
    return sorted(results)


@PromptServer.instance.routes.get("/misaka/rvc_model_list")
async def get_rvc_model_list(request):
    return web.json_response(_scan_files(".pth"))


@PromptServer.instance.routes.get("/misaka/rvc_index_list")
async def get_rvc_index_list(request):
    return web.json_response(_scan_files(".index"))


__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]

WEB_DIRECTORY = "js"
