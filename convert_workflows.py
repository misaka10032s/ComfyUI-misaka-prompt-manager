import os
import json

# 定義路徑
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
COMFY_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "../../"))

# 兩個來源資料夾名稱
SOURCE_FOLDERS = ["boleromixPony_v210", "novaAnimeXL_ilV140"]
WORKFLOWS_BASE = os.path.join(COMFY_ROOT, "user", "default", "workflows", "old")
DEST_DIR = os.path.join(COMFY_ROOT, "user", "default", "misaka-prompt-sets")

def process_output_name(val):
    if not val or not isinstance(val, str):
        return ""
    # Transform "asd/qwe/zxc" -> "qwe/zxc"
    idx = val.find('/')
    if idx != -1:
        return val[idx+1:]
    return val

def convert_file(file_path, relative_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return

    nodes = data.get("nodes", [])
    profile = {
        "checkpoint": "",
        "loras": [],
        "character": "",
        "H": "",
        "expression": "",
        "pose": "", 
        "scene": "",
        "negative": "", 
        "output_name": "",
        "clip_skip": 0
    }
    
    for node in nodes:
        node_type = node.get("type")
        title = node.get("title", "")
        widgets = node.get("widgets_values", [])
        
        if not widgets: continue
        val_str = str(widgets[0]) if widgets[0] is not None else ""
        
        if node_type == "CheckpointLoaderSimple":
            profile["checkpoint"] = val_str
        elif node_type == "LoraLoader":
            l_name = val_str
            if l_name != "None":
                l_model = 1.0
                l_clip = 1.0
                if len(widgets) > 1:
                    try: l_model = float(widgets[1])
                    except: pass
                if len(widgets) > 2:
                    try: l_clip = float(widgets[2])
                    except: pass
                profile["loras"].append({
                    "name": l_name,
                    "strength_model": l_model,
                    "strength_clip": l_clip
                })
        elif title == "角色設定":
            profile["character"] = val_str
        elif title == "色色":
            profile["H"] = val_str
        elif title == "表情姿勢":
            profile["expression"] = val_str
        elif title == "其他場景":
            profile["scene"] = val_str
        elif node_type == "SaveImage":
            profile["output_name"] = process_output_name(val_str)
        elif title == "暫存":
            profile["note"] = val_str

    # 計算目標路徑：misaka-prompt-sets / 相對路徑
    dest_path = os.path.join(DEST_DIR, relative_path)
    
    try:
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        with open(dest_path, 'w', encoding='utf-8') as f:
            json.dump(profile, f, indent=4, ensure_ascii=False)
        print(f"Converted: {relative_path}")
    except Exception as e:
        print(f"Error saving {dest_path}: {e}")

def main():
    total_count = 0
    for folder in SOURCE_FOLDERS:
        src_root = os.path.join(WORKFLOWS_BASE, folder)
        if not os.path.exists(src_root):
            print(f"Folder not found, skipping: {src_root}")
            continue

        print(f"Scanning recursively: {src_root}")
        
        # 遞歸掃描 (Recursive Scan)
        for root, dirs, files in os.walk(src_root):
            for filename in files:
                if filename.endswith(".json"):
                    full_path = os.path.join(root, filename)
                    
                    # 計算相對路徑 (相對於 WORKFLOWS_BASE)
                    # 例如: full = .../workflows/boleromix/A/b.json
                    # base = .../workflows
                    # rel = boleromix/A/b.json
                    rel_path = os.path.relpath(full_path, WORKFLOWS_BASE)
                    
                    convert_file(full_path, rel_path)
                    total_count += 1
            
    print(f"\nConversion complete. Processed {total_count} files.")

if __name__ == "__main__":
    main()