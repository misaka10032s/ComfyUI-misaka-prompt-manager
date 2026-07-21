---
id: BP-API-1
title: REST 路由 + Profile 路徑防護（path traversal 防禦）
system: api
tags: [aiohttp, security, path-traversal, rest]
status: 已測試
request_verbatim: >-
  「load_profile, save_profile (__init__.py) and MisakaImagePromptManager.load joined an
  unnormalised user-supplied name onto the storage root, allowing read/write of arbitrary
  .json outside storage via ../.., absolute paths or null bytes.」（git commit cab4ac0
  訊息，修復動機逐字；REST 路由本身的初始需求無獨立逐字稿，見各路由 revisions 引用的
  commit）
decided_date: 2026-01-25
exec_links:
  - __init__.py（五條 /misaka/* 路由）
  - nodes/image/factory/_paths.py（resolve_profile_path）
  - nodes/image/factory/prompt_manager.py（load() 呼叫端）
  - tests/test_path_traversal.py
depends_on:
  - BP-IMG-1
done_date: 2026-06-20
tests:
  - date: 2026-07-21
    target: "nodes/image/factory/_paths.py › resolve_profile_path()（獨立 dep-free 模組，測試不需載入 torch/comfy）"
    action: "python tests/test_path_traversal.py（repo root 直接執行；5 個測試：合法名稱、相對路徑跳出如 ../../x／..\\..\\x／foo/../../bar／../secret、絕對路徑如 /etc/passwd／C:\\Windows\\...／D:\\secret\\...、null byte、None）"
    expected: "合法名稱正常解析且落在 storage root 內；所有跳出/絕對路徑/null byte/None 皆丟 ValueError 或被 commonpath 檢查攔在 base 內"
    result: "PASS — 5/5（實際輸出：'PASS test_absolute_path_rejected' / 'PASS test_none_rejected' / 'PASS test_null_byte_rejected' / 'PASS test_relative_traversal_rejected' / 'PASS test_simple_name_ok' → 'ALL PASSED'）"
    evidence: tests/test_path_traversal.py
    executor: implementer-subagent（本次 P2 blueprint seeding，2026-07-21 重新執行驗證）
revisions:
  - date: 2026-06-20
    summary: "commit cab4ac0 — 新增 nodes/image/factory/_paths.py:resolve_profile_path()（realpath + os.path.commonpath 檢查），套用於 __init__.py 的 /misaka/save_profile /misaka/load_profile 與 MisakaImagePromptManager.load()；新增 tests/test_path_traversal.py 五個測試。**注意**：MisakaImageProfileFactory.execute() 的節點內建存檔路徑（save_as_profile widget）未套用此修復，仍是開放缺口——詳見 BP-IMG-1「已知問題」段"
origin: "git commit cab4ac0 訊息 + tests/test_path_traversal.py"
---

## 設計說明

外掛在 ComfyUI 的 aiohttp 伺服器上新增 5 條 `/misaka/*` REST 路由（`__init__.py`），供
`js/image_factory.js`（見 BP-UI-1）與 `js/voice.js`（見 BP-UI-4）呼叫：

| 路由 | 方法 | 用途 | 使用者輸入 | 是否需路徑防護 |
|---|---|---|---|---|
| `/misaka/profile_list` | GET | 遞迴列出 storage 底下所有 `.json`（相對路徑） | 無 | 否（只回既有清單） |
| `/misaka/load_profile` | GET | `?name=` 讀取指定 profile | `name`（query） | **是** |
| `/misaka/save_profile` | POST | `{filename, data}` 寫入指定 profile | `filename`（body） | **是** |
| `/misaka/rvc_model_list` | GET | 遞迴列出 `models/rvc` 底下 `.pth` | 無 | 否 |
| `/misaka/rvc_index_list` | GET | 遞迴列出 `models/rvc` 底下 `.index` | 無 | 否 |

### `resolve_profile_path()`（`nodes/image/factory/_paths.py`，2026-06-20 `cab4ac0`）

無外部依賴的小模組（不 import torch/comfy,方便單元測試獨立執行）：

```python
def resolve_profile_path(base, name, suffix=".json"):
    # 拒絕 None、null byte
    # realpath(base) 與 realpath(join(base, name+suffix)) 比較
    # os.path.commonpath([base_real, candidate]) != base_real → ValueError
```

`load_profile`/`save_profile`（`__init__.py`）與 `MisakaImagePromptManager.load()`
三個呼叫端都已套用（見 revisions）。修復前,`../../x`、絕對路徑（`/etc/passwd` 等）、
null byte 皆可能讀寫到 storage root 之外。

### 已知殘留缺口

`MisakaImageProfileFactory.execute()` 的節點內建存檔路徑（`save_as_profile` widget）
**未套用**此防護 — 詳見 BP-IMG-1「已知問題」段的完整分析與 mermaid 流程圖（存檔路徑 B）。
此為本次 blueprint 盤點新發現的落差,非本條目測試範圍內的既有已知問題重複記錄。

## 驗證方式（本次 P2 blueprint seeding 重新確認，2026-07-21）

```
python tests/test_path_traversal.py
```
5 個測試（`test_simple_name_ok` / `test_relative_traversal_rejected` /
`test_absolute_path_rejected` / `test_null_byte_rejected` / `test_none_rejected`）獨立
import `_paths.py`（`importlib.util.spec_from_file_location`,不拉入 torch/comfy),
可在任何 Python 3 環境執行,不需要 ComfyUI 運行環境。**注意**：`python -m pytest
tests/test_path_traversal.py` 在此 repo 會因 repo root 的 `__init__.py`（ComfyUI 外掛
entry point,import `.nodes.image` 等相對路徑）被 pytest 誤判為套件根而收集失敗
（`ImportError: attempted relative import with no known parent package`）——這是既有的
pytest rootdir 判定問題,不是 `_paths.py` 或測試本身的缺陷,測試檔案 docstring 本身也記載了
「不用 pytest」的替代執行方式；本條目採用該替代方式驗證。
