from .misaka_node import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS, get_storage_path
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
                    # Relative path for nested folders
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
    # Security check? name should be relative.
    path = os.path.join(base, name + ".json")
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
        
        # Determine path based on checkpoint
        if filename.startswith("/") or filename.startswith("\\"):
            # Absolute relative to base (remove leading slash)
            relative_save_path = filename.lstrip("/").lstrip("\\")
        else:
            # Prefix with checkpoint name
            ckpt_name = profile_data.get("checkpoint", "")
            if ckpt_name:
                model_stem = os.path.splitext(os.path.basename(ckpt_name))[0]
                relative_save_path = os.path.join(model_stem, filename)
            else:
                relative_save_path = filename

        save_path = os.path.join(base, relative_save_path + ".json")
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        
        with open(save_path, 'w', encoding='utf-8') as f:
            json.dump(profile_data, f, indent=4, ensure_ascii=False)
            
        return web.Response(status=200, text="Saved successfully")
    except Exception as e:
        return web.Response(status=500, text=str(e))

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS', 'WEB_DIRECTORY']

WEB_DIRECTORY = "js"