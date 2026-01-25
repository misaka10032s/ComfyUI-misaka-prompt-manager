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

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS', 'WEB_DIRECTORY']

WEB_DIRECTORY = "js"