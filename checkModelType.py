import requests
from bs4 import BeautifulSoup
import os
import json
import re
import shutil

headers = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "no-cache",
    "Cookie": "_ga=GA1.1.786068668.1753111239; _sharedID=d7bb0257-0472-4965-83a5-af83d4f49f1f; _sharedID_cst=TyylLI8srA%3D%3D; _cc_id=d7ea4ede8dfabcc3bdc034a720fbadb; _ga_N6W8XF7DXE=GS2.1.s1755013561$o7$g0$t1755013561$j60$l0$h0; _sharedID_last=Tue%2C%2012%20Aug%202025%2015%3A46%3A01%20GMT; cto_bundle=0ol4-F9JTTAwVnRiTzVvcHFVbllYVExwWU1CVlRiaHhqM1AlMkJsQ2hhZVVLbkxtVyUyRk9zbGx3NUFNdVNJRDJCayUyQnAwNWphWEd6RFkySkFGdjFvbUl4ZCUyQjVGMmR4bXRYTmtKeHhsJTJGQ0M1V3AzTEhIRXB4VzFxc0VrSWxOb3NFQ2JOYjNxaGNSSlRTRDgwRXR4OVBRRWZaZmRmdnFBJTNEJTNE; __gads=ID=57041dbf11803236:T=1753111260:RT=1755013564:S=ALNI_MZXBHjiV23Jjs5dYGrq8TrQoyRmog; __gpi=UID=0000116b79eb65d3:T=1753111260:RT=1755013564:S=ALNI_MbKvJ10CrdOPV9RvRjAixpS5QynDA; __Secure-next-auth.callback-url=https%3A%2F%2Fcivitai.com; __Host-next-auth.csrf-token=5777c95c40e157189cd76e2e2a9d034a77052c9f4d7dfb58e9e6f864089f0ec7%7C31949fb39d78197d31c15e40ba028d41c5b87f313d98400d295f23372e0d0b7c; ref_landing_page=%2Fmodels%2F1702547%3FmodelVersionId%3D2240221; civitai-route=2da8068feec31830bc60402117dab99f|bf4092ed2cc1ac81a1918599cbb73e8c; __Secure-civitai-token=eyJhbGciOiJkaXIiLCJlbmMiOiJBMjU2R0NNIn0..cKPsxSI2LreKXxje.x3Z7M0_yxS-DQjOCx_x3W7n1ktUWHaxoC61Yu0sIa0Y8T5-JF3WlhJxI04Rub3W8nmVyCcOHTU1Hg4t_rK0x8w9Bd2yaPopB5jQyxEz02vKWbHVY0T2gL3PaWUM3DdWT_wvQNA4SzJjbuEsQzv7aC3EPYtQpG55kpiA-C06I0cR5UCUA3bZ-MMjtao6a8n-yPCudxB4z30wzKcbjkATaAeImkKUmQeK-c7hIWPVmx66X1SoYrlFYfPHekiL0uaQgsLvDjXx0X61zBltO69hT6MEWiyJxDVm7dI7nma0dmRYLLKR-QQqQPiL6Hj-s-vDTS_DnVWfO6pgrv-9lnoX66tmaLrIuxYTREpEvKVeU-1UteHzMxwz1vlxYS5iNHrQlrAQ9GO_OpDUq8k0ptojELkNAPcSZ1im0PcchzPqUM74hWrDNscRP-YsdycLcEL28pjXAZHy4nKsHtW0hGmtWI6R-tQxj8gghJ6piAvOfAtsKJQpVDU7bRgoDDvl-A5uJxLGZ2C_ZLaaEkX6TsHcml7L4D8amcu9pqcg1dNpccKHeacvFV2IFI_NzLANUQG0_YxV06iwueOMAUYrHQpHskpYoL9LUHZ39zpp9MMFTWdN4WTYe9Epg_-39aAOYqr2X3m8lLQjAhfGo-PSra2UNqwT0UgZf2J0ulhn1Osthi9k2oyLYWwxCIEbgVlXNkFrCGnwqM7UuDS9_gKpsZZZWlx5QlC_kgE9WA3xoVEpQ-zHFjJD-_V_OHaDEGv7XHZiW27mN9__CatrSShWB5ilRJnzy0iglABwh8dow7DXBZJpxnRc7GuBJ9ecERB-qkLWl-KyJB7PBs98KVE27I3Y5kGVvTRYm0xGX6k5voG-gwYbhqPHvnO9z8jl1Lq0tiblS2rlcRgPYQqFV3szfJzlNcB6maPmBTB3jEYYaNkttbhfOqe3P7C43NmkTHgRKfjU8xysKRwmTFLoNCE88BJrwfWptB0ZD24AEC1htJQjsyqb2U3k_b2Om6XDUr7bvYucrAZ6UYblyJ_1BYinFLl0GFBsLECsJ_De509dw1botl5AgP68xkXF6LPWiRcPjiaHUc9t6Q5cVaJOrnNg29kb81gZ1Ix_k4MY7UPTiCs9H4_ccg4lhtNGfwA1_phkT7ncPLBmQQunezmLaoOzSw3ATvyBc7W43nFGg55y_jhmQl2kJscZ7sDvo9qrBIhMclU2Lan2fObjDaoLEIpGSXklTJWKNLl4n8WEAKme_Pl5AuJ7cYxbB6n29zudI2FPqr-b46fG6X9doIYQFoD2DLEPU8jKPWwXH5tiMC8AnSjL87allvgulT9SxSeyS9Mq4cmwiE2ozAi28C78.BQSiMAs-2jePcIyO4VAx1Q",
    "Pragma": "no-cache",
    "Priority": "u=0, i",
    "Sec-CH-UA": '"Not(A:Brand";v="8", "Chromium";v="144", "Google Chrome";v="144"',
    "Sec-CH-UA-Mobile": "?0",
    "Sec-CH-UA-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
}

# --- Configuration ---
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
COMFY_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "../../"))
MISAKA_SETS_DIR = os.path.join(COMFY_ROOT, "user", "default", "misaka-prompt-sets")

PONY_FOLDER = "boleromixPony_v210"
ILLUSTRIOUS_FOLDER = "novaAnimeXL_ilV140"

PONY_CKPT = "boleromixPony_v210.safetensors"
ILLUSTRIOUS_CKPT = "novaAnimeXL_ilV140.safetensors"

ILLUSTRIOUS_KEYWORD = "Illustrious"
PONY_KEYWORD = "Pony"
ILLUSTRIOUS_CHECKPOINT_KEY = "novaAnimeXL_ilV140"
PONY_CHECKPOINT_KEY = "pony"


# --- Network & Parsing ---
def fetch_page(url):
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return BeautifulSoup(response.text, 'html.parser')
    except requests.RequestException as e:
        print(f"Error fetching {url}: {e}")
        return None
    
def find_model_type_from_soup(model_page_soup):
    tbody = model_page_soup.find('tbody', class_='mantine-Table-tbody')
    if not tbody:
        return None
    for tr in tbody.find_all('tr'):
        tds = tr.find_all('td')
        if len(tds) >= 2 and tds[0].get_text(strip=True) == "Base Model":
            return tds[1].get_text(strip=True)
    return None

def find_model_type(url):
    soup = fetch_page(url)
    if soup:
        return find_model_type_from_soup(soup)
    return None

def extract_civitai_urls(text):
    if not text:
        return []
    return re.findall(r'(https://civitai\.com[^\s\u4e00-\u9fa5]*)', text)


# --- File Operations ---
def move_and_update_file(full_path, rel_path, expected_type):
    # Determine target
    if "Pony" in expected_type:
        target_root_folder = PONY_FOLDER
        target_ckpt = PONY_CKPT
    elif "Illustrious" in expected_type:
        target_root_folder = ILLUSTRIOUS_FOLDER
        target_ckpt = ILLUSTRIOUS_CKPT
    else:
        print(f"  [Skip] Unknown expected type: {expected_type}")
        return False

    # Construct target path
    parts = rel_path.split(os.sep)
    if len(parts) < 2:
        print(f"  [Skip] Invalid relative path structure: {rel_path}")
        return False

    # Replace root folder in path
    parts[0] = target_root_folder
    target_rel_path = os.path.join(*parts)
    target_full_path = os.path.join(MISAKA_SETS_DIR, target_rel_path)

    # If source and target are the same, just update json if needed
    if os.path.normpath(full_path) == os.path.normpath(target_full_path):
        # Just update JSON ckpt if needed
        return update_json_ckpt(full_path, target_ckpt)

    print(f"  [Move] {rel_path} -> {target_rel_path}")
    
    target_dir = os.path.dirname(target_full_path)
    if not os.path.exists(target_dir):
        os.makedirs(target_dir, exist_ok=True)

    try:
        shutil.move(full_path, target_full_path)
    except Exception as e:
        print(f"  [Error] Moving file: {e}")
        return False

    return update_json_ckpt(target_full_path, target_ckpt)

def update_json_ckpt(file_path, target_ckpt):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        old_ckpt = data.get("checkpoint", "")
        if old_ckpt != target_ckpt:
            data["checkpoint"] = target_ckpt
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            print(f"  [Update] Checkpoint updated: '{old_ckpt}' -> '{target_ckpt}'")
            return True
        else:
            print("  [OK] Checkpoint already matches.")
            return True
            
    except Exception as e:
        print(f"  [Error] Updating JSON {file_path}: {e}")
        return False

def remove_empty_folders(path):
    if not os.path.isdir(path):
        return

    # Bottom-up walk to remove nested empty dirs
    for root, dirs, files in os.walk(path, topdown=False):
        for name in dirs:
            full_path = os.path.join(root, name)
            try:
                if not os.listdir(full_path):
                    print(f"Removing empty folder: {full_path}")
                    os.rmdir(full_path)
            except OSError as e:
                print(f"Error removing {full_path}: {e}")

# --- Main Logic ---
def main():
    if not os.path.exists(MISAKA_SETS_DIR):
        print(f"Directory not found: {MISAKA_SETS_DIR}")
        return

    print(f"Scanning files in: {MISAKA_SETS_DIR}")
    
    # We collect files first to avoid modifying the directory structure while walking it
    files_to_process = []
    for root, dirs, files in os.walk(MISAKA_SETS_DIR):
        for filename in files:
            if filename.endswith(".json"):
                full_path = os.path.join(root, filename)
                rel_path = os.path.relpath(full_path, MISAKA_SETS_DIR)
                files_to_process.append((full_path, rel_path))

    processed_count = 0
    moved_count = 0

    for full_path, rel_path in files_to_process:
        # Re-check existence in case previous moves affected it (unlikely if strictly tree-walking, but safe)
        if not os.path.exists(full_path):
            continue

        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            print(f"Error reading {rel_path}: {e}")
            continue

        note = data.get("note", "")
        checkpoint = data.get("checkpoint", "")
        urls = extract_civitai_urls(note)

        # Assuming we check the first valid URL
        for url in urls:
            try:
                # print(f"Checking: {rel_path}...")
                model_type = find_model_type(url)
                if not model_type:
                    continue

                is_pony_web = PONY_KEYWORD.lower() in model_type.lower()
                is_illustrious_web = ILLUSTRIOUS_KEYWORD.lower() in model_type.lower()
                
                needs_move = False
                expected_type = ""

                if is_pony_web:
                    # Check if currently in pony folder or has pony ckpt
                    if PONY_CHECKPOINT_KEY.lower() not in checkpoint.lower():
                        needs_move = True
                        expected_type = "Pony"
                elif is_illustrious_web:
                    # Check if currently in illustrious folder or has illustrious ckpt
                    if ILLUSTRIOUS_CHECKPOINT_KEY not in checkpoint:
                        needs_move = True
                        expected_type = "Illustrious"

                if needs_move:
                    print(f"Mismatch found in: {rel_path}")
                    print(f"  Expected: {expected_type}, Got: {checkpoint} (Web: {model_type})")
                    if move_and_update_file(full_path, rel_path, expected_type):
                        moved_count += 1
                
                # If valid model type found, break loop (process only once per file)
                if is_pony_web or is_illustrious_web:
                    break

            except Exception as e:
                print(f"Error processing URL {url} in {rel_path}: {e}")

        processed_count += 1

    print(f"\nProcessed {processed_count} files.")
    print(f"Moved/Updated {moved_count} files.")
    
    print("\nCleaning up empty directories...")
    remove_empty_folders(MISAKA_SETS_DIR)
    print("Done.")

if __name__ == "__main__":
    main()