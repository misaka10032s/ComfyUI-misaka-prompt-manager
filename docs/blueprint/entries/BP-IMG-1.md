---
id: BP-IMG-1
title: Profile 存取（Factory 建立/編輯/儲存 + Manager 載入）
system: img
tags: [profile, checkpoint, lora, prompt, save-load]
status: 已完成
request_verbatim: >-
  「我正在使用comfyUI來產生一系列圖片，但是管理prompt卻成一大問題...現在我是用
  /{checkpointName}/{角色分類}/{角色名字}/{動作場景} 這樣用一堆資料夾分類，但這樣有點亂。
  我需要一個custom node，可以讓分類簡化成 {角色分類}/{角色名字} 然後使用那個node來切換不同的
  checkpoint + lora + outputName...custom output point要有: MODEL, CLIP, VAE, TEXT...
  我希望這個node存的資料會在外部...而不是跟node程式碼放在一起」
  （逐字稿見 repo root `prompt` 檔案第 1–13 行，先於 git 初始化）
decided_date: 2026-01-25
exec_links:
  - prompt（原始需求逐字稿，repo root）
  - nodes/image/factory/profile_factory.py
  - nodes/image/factory/prompt_manager.py
  - nodes/image/factory/_shared.py
  - nodes/image/factory/_paths.py
  - nodes/image/factory/_origin_guard.py（同源檢查＋body 大小上限，2026-09-07，待回答 #47）
  - js/image_factory.js（前端動態 UI，見 BP-UI-1）
  - __init__.py（REST 路由 /misaka/save_profile /misaka/load_profile，見 BP-API-1）
done_date: 2026-06-20
revisions:
  - date: 2026-01-26
    summary: "commit 5ff89dc / e1ddedc / 54883b4 — 新增存/讀按鈕、資料夾篩選選單、note 欄位存讀邏輯（把 workflow 中 title=\"note\" 的 CLIPTextEncode 節點值存進/寫回 profile）"
  - date: 2026-02-15
    summary: "commit a78cd58 — 儲存路徑加上 images/ 前綴"
  - date: 2026-05-24
    summary: "commit b13acaa — 由單一 misaka_node.py 拆分為 nodes/image/factory/ 套件，類別重新命名為 MisakaImageProfileFactory / MisakaImagePromptManager"
  - date: 2026-06-20
    summary: "commit cab4ac0 — 修復 path traversal：新增 nodes/image/factory/_paths.py:resolve_profile_path()（realpath + os.path.commonpath 校驗），套用於 __init__.py 的 /misaka/save_profile /misaka/load_profile 路由與 MisakaImagePromptManager.load()。注意：MisakaImageProfileFactory.execute() 的 save_as_profile 節點內建存檔路徑**未套用此修復**（見下方「已知問題」）"
  - date: 2026-07-22
    summary: "commit 3ce3b4a — 補上 MisakaImageProfileFactory.execute() 的 save_as_profile 節點存檔路徑防護：改用 resolve_profile_path()（與 cab4ac0 的路由/Manager 相同函式），拒絕時走既有 except 分支（記錄 log、不寫檔），行為與路由一致。缺口已關閉（見下方「已修復」）"
origin: "prompt（repo root，需求逐字稿）"
tests:
  - date: 2026-07-22
    target: "nodes/image/factory/profile_factory.py › MisakaImageProfileFactory.execute() 的 save_as_profile 節點存檔路徑"
    action: "python tests/test_path_traversal.py（新增 test_node_save_traversal_rejected／test_node_save_normal_name_still_saves；透過 stub folder_paths/comfy.sd/comfy.utils 驅動 execute()，不需真實 ComfyUI 安裝）"
    expected: "跳出路徑（../escaped／..\\escaped／../../escaped）遭 resolve_profile_path() 拒絕、storage root 外無任何檔案落地；一般名稱（my_profile）仍正常存檔於 base/my_profile.json"
    result: "PASS — 7/7（off-by-one 訂正 2026-09-05，CLAUDE.md:39 自身即載明 7 tests；修復前先跑出 RED：test_node_save_traversal_rejected 因 '../escaped' 逃逸至 storage root 外而 FAIL，證明缺口存在；套用修復後全數 PASS，含既有 5 個測試）"
    evidence: tests/test_path_traversal.py
    executor: implementer-subagent（BP-IMG-1 security fix，2026-07-22）
  - date: 2026-09-07
    target: "nodes/image/factory/_origin_guard.py（check_same_origin／guard_same_origin／read_capped_body），套用於 __init__.py 的 POST /misaka/save_profile 路由"
    action: "quality-gates/run.py l0（G1 ruff／G2 mypy／G3 pytest／G3b assertion-presence，py -3.11，cwd=repo root）；pytest 直接執行 tests/test_origin_guard.py（同 tests/test_path_traversal.py 的 spec_from_file_location 直讀手法，不經過會拉入真實 ComfyUI 的 root __init__.py）"
    expected: "同源 Origin 通過；跨站 Origin／null Origin／Origin 缺 Host／Origin 與 Host 埠號不符 均 403；無 Origin 時 Sec-Fetch-Site: cross-site 403、其餘通過；Host 埠號與伺服器實際埠號（server_port）不符 403（訂正 2026-09-07：此僅為次要輔助檢查，非 DNS-rebinding 主防線，見下方新增 tests／qa_log 記錄）；GET 等唯讀方法不受此檢查影響；request body 超過 1 MiB（content-length 與串流兩種路徑）均 413"
    result: "PASS — quality-gates/run.py l0 全綠：[G1] PASS — 24 total violation(s), 0 new vs baseline (24 pre-existing). ｜ [G2] PASS — 23 total error(s), 0 new vs baseline (23 pre-existing). ｜ pytest：30 passed（含既有 test_path_traversal.py 7 個 + 新增 test_origin_guard.py 23 個）｜ [G3b] PASS — 1 changed test file(s), all touched test functions assert something。未修改 quality-gates/ruff-baseline.json 或 mypy-baseline.json 任何一筆（新增的 4 個 re-export 改用 redundant-alias 寫法避免產生新的 mypy/ruff baseline 需求，理由見 nodes/image/factory/__init__.py 內註解）"
    evidence: tests/test_origin_guard.py
    executor: implementer-subagent（待回答 #47 security fix，2026-09-07）
  - date: 2026-09-07
    target: "nodes/image/factory/_origin_guard.py（新增 _host_hostname_permitted／_parse_allowed_hosts_env／content_length_exceeds_cap；修正 _parse_origin／_log_rejected_origin），套用於 __init__.py 的 POST /misaka/save_profile 路由"
    action: "opus fresh-review（27859b4）F1–F6 修復（fix pass）：quality-gates/run.py l0（py -3.11，cwd=repo root）；pytest tests/test_origin_guard.py（cwd=tests，--rootdir=. --confcutdir=.，同 quality-gates/run.py g3 的實際呼叫方式）"
    expected: "F1 DNS-rebinding：Host 主機名稱非 IP 位址／localhost 且未列於 MISAKA_PM_ALLOWED_HOSTS 一律 403（含 Origin／Host 相符且埠號亦相符的偽裝案例）；MISAKA_PM_ALLOWED_HOSTS 可白名單放行指定主機名稱；畸形清單項目（含 *、scheme://、host:port、user@host 形式）一律丟棄且不誤放行；127.0.0.1／[::1]／localhost／0.0.0.0／LAN IP／結尾句點寫法均仍放行。F2 畸形 Origin 埠號（非數字後綴／超出範圍）一律回 (False, reason)，不拋出例外，guard_same_origin() 端到端回 403 JSON 而非 500。F3 _warned_origins 不無限增長。F4 content_length_exceeds_cap() 直接測試 handler 真正呼叫的判斷式，不再只驗證 aiohttp 自身的 Content-Length 解析。F5 移除未使用的 _mocked_request_with_body。"
    result: "PASS — quality-gates/run.py l0 全綠：[G1] PASS — 24 total violation(s), 0 new vs baseline (24 pre-existing). ｜ [G2] PASS — 23 total error(s), 0 new vs baseline (23 pre-existing). ｜ pytest：55 passed（既有 test_path_traversal.py 7 個 + tests/test_origin_guard.py 48 個，較前次 23 個新增 25 個）｜ [G3b] PASS — 1 changed test file(s), all touched test functions assert something。quality-gates/ruff-baseline.json、mypy-baseline.json 均未變動（git diff --stat 為空）"
    evidence: tests/test_origin_guard.py
    executor: implementer-subagent（opus fresh-review F1–F6 fix pass，2026-09-07）
qa_log:
  - date: 2026-09-07
    summary: >-
      待回答 #47：ComfyUI 本身沒有內建驗證機制，任何使用者開啟的網頁都能對掛載在共用
      aiohttp PromptServer 上的 REST 路由發出跨站請求；本 repo 唯一的寫入路由
      POST /misaka/save_profile 原本沒有 request body 大小上限（稽核發現 A-comfy-2：
      可被用來塞爆磁碟）。Owner 裁示「五個都做」（cluster 內五個受影響 repo 全部修復，
      本 repo 為第 5 個）。決策：採「同源檢查」而非其他 repo 慣用的 loopback
      allow-list——因為 ComfyUI 常以 --listen 綁定 LAN IP 供區網內其他機器的瀏覽器存取，
      loopback 允許清單會誤擋這個合法用例；若改成「允許 --listen 指定的 host」則等同
      「相信操作者已核准的任何來源」，並非真正的 CSRF 防護。改為檢查請求的 Origin
      （或在 Origin 缺席時退回 Sec-Fetch-Site）是否確實指向本機正在執行的這個 ComfyUI
      實例本身，並另外驗證 Host 標頭的埠號與伺服器實際綁定埠號一致，不論 ComfyUI
      綁定在哪個網路介面上都成立。【2026-09-07 訂正，見下方新增 qa_log 記錄】本段原本
      將上述埠號檢查稱為「DNS-rebinding 防護」，經 opus fresh-review 指出這是錯的：
      DNS-rebinding 攻擊者同時控制網域與其代管頁面的埠號，只要把頁面開在 ComfyUI
      的預設埠（8188）上，Origin／Host 兩者就會互相吻合、埠號也會與 server_port 相符，
      此埠號檢查形同虛設。真正的 DNS-rebinding 防護（要求 Host 主機名稱本身必須是 IP
      位址或 localhost）已於同日的修復回合補上，原埠號檢查降級為次要輔助層。變更檔案：
      nodes/image/factory/_origin_guard.py（新增，pure function check_same_origin
      +aiohttp helper guard_same_origin+body 上限工具 read_capped_body/BodyTooLarge，
      含模組 docstring 說明本決策理由）、nodes/image/factory/__init__.py（re-export，
      避免在 __init__.py 產生新的 mypy「__main__.nodes.image.factory._origin_guard」
      structural-artifact baseline 條目）、__init__.py（save_profile 路由套用同源檢查與
      body 大小上限）、tests/test_origin_guard.py（新增）。Body 大小上限：
      MAX_PROFILE_BODY_BYTES = 1 MiB（1048576 bytes），對 request.content_length
      （快速路徑）與實際串流讀取（防止用 chunked transfer 或偽造 Content-Length 繞過）
      都有檢查，超過回 413；profile_data 序列化後的大小也另外檢查。前端
      js/image_factory.js 的 save_profile fetch 呼叫確認本來就是同源相對路徑
      （fetch("/misaka/save_profile")），未做變更。
  - date: 2026-09-07
    summary: >-
      待回答 #47 fresh-review 修復回合（opus，fresh context，未寫過上一輪程式碼）對
      27859b4 的複核結果：VERDICT CHANGES-NEEDED，列出 F1–F9 共 9 項發現，其中 F1／F2
      判定為 blocking。F1（Medium）：原本的 Host 埠號檢查被誤稱為「DNS-rebinding
      防護」，實際上完全無效——攻擊者只要把自己的網頁開在 ComfyUI 預設埠（8188）上，
      Origin／Host 便會互相吻合、埠號也與 server_port 相符，該檢查對此無感（live probe
      E19 證實：Host/Origin 均為 attacker.example:8188 時回 200，成功寫入檔案）。修復：
      新增 _host_hostname_permitted()，要求 Host 主機名稱必須是 IP 位址（含 IPv6，
      去除中括號、忽略結尾句點）或 localhost，否則一律拒絕；新增環境變數
      MISAKA_PM_ALLOWED_HOSTS（逗號分隔的裸主機名稱，禁止 scheme/port/path/萬用字元
      `*`，畸形項目丟棄並記一次 WARNING）作為反向代理／主機名稱存取的白名單退路，
      因此類部署（如 comfy.example.com 或 mypc.local）在未設定此環境變數前會對每次
      save_profile 一律 403——此為刻意的安全取捨，已記於模組 docstring。原埠號檢查
      保留，改標示為次要輔助層（非 rebinding 主防線）。F2（Low-Medium）：畸形 Origin
      埠號（例如 http://127.0.0.1:8188.evil.example 或超出 0-65535 範圍）會讓
      SplitResult.port 延遲拋出 ValueError，且該存取點原本落在既有 try/except 之外，
      導致整個 guard 未經捕捉地拋出例外，端到端會變成 500 而非 403（live probe E20／
      E21 證實）。修復：把 parts.scheme/hostname/port 的存取全部移進同一個
      try/except ValueError 區塊。F3（Low，非 blocking）：_warned_origins 為模組層級
      set，理論上可被惡意客戶端用大量不同 Origin 值撐爆記憶體；修復：達到
      _MAX_WARNED_ORIGINS=256 後停止繼續加入（仍照常記 log，只是不再去重）。F4
      （Low，非 blocking）：新增測試 test_content_length_over_cap_detected_without_
      reading_body 原本只驗證 aiohttp 自己解析 Content-Length 標頭的行為，即使
      __init__.py 的 content_length 快速路徑被整段刪除，該測試仍會通過——不構成
      handler 行為的證據。修復：把該判斷式抽成獨立可測函式
      content_length_exceeds_cap()，__init__.py 改呼叫此函式，測試改為直接呼叫它
      （並補上「等於上限不算超過」「None 不算超過」兩個邊界案例）。F5（Info）：
      刪除未被任何測試呼叫的 _mocked_request_with_body() 測試輔助函式。F6（Info，
      文件化即可，非程式變更）：F1 修復後的 accepted trade-off（TLS 終止或走主機名稱
      的反向代理、以及未加入白名單的 LAN mDNS 主機名稱存取，一律 403）已記入
      nodes/image/factory/_origin_guard.py 模組 docstring 與本檔案上方 qa_log
      2026-09-07 條目的訂正段落。F7／F8／F9 為 Info／非缺陷記錄，未要求變更。修復後
      quality-gates/run.py l0 全綠、pytest 55 passed（較複核時的 30 passed 新增 25
      個測試，覆蓋 F1 的 DNS-rebinding／MISAKA_PM_ALLOWED_HOSTS 白名單／畸形清單項目
      丟棄／既有合法主機型態全數仍放行，以及 F2 的兩種畸形 Origin 埠號皆回 403 而非
      拋出例外，含 guard_same_origin() 端到端層級的驗證）。變更檔案：
      nodes/image/factory/_origin_guard.py（F1／F2／F3／F4／F6 docstring 訂正）、
      nodes/image/factory/__init__.py（re-export content_length_exceeds_cap）、
      __init__.py（save_profile 改呼叫 content_length_exceeds_cap()）、
      tests/test_origin_guard.py（新增 F1／F2／F3 測試、重寫 F4 的失效測試、刪除 F5
      的死碼）、docs/blueprint/entries/BP-IMG-1.md（本條目 + 上方 tests／qa_log
      2026-09-07 條目的訂正段落）。
---

## 設計說明

管理「checkpoint + LoRA(s) + 分類 prompt」的可重複使用設定檔（profile），取代原本用一堆資料夾
分類（`/{checkpoint}/{角色分類}/{角色名字}/{動作場景}`）的手動流程。兩個節點構成存取的一體兩面：

- **Misaka Image Profile Factory（Editor/Saver）**——建立、編輯、儲存 profile。
- **Misaka Image Prompt Manager（Loader）**——列出並載入已存的 profile。

兩者共用 `nodes/image/factory/_shared.py` 的 `apply_assets()`（載入 checkpoint + 逐一套用
LoRA + 依 `clip_skip` 做 CLIP 分層跳過 + 編碼 prompt）與 `process_output_name()`（輸出檔名模板
解析,見下方）。

### Factory 欄位與存檔邏輯

`INPUT_TYPES`：`checkpoint`（下拉）、`character`/`H`/`expression`/`pose`/`scene`（五個多行分類
prompt 欄位，取代舊版單一 `positive` 字串）、`output_name`、`save_as_profile`、`clip_skip`；
`optional`：`lora_1` + 對應 strength（UI 動態擴充多組，見 BP-UI-1）、`node_map`/`lora_data`（隱藏，
由 JS `onSerialize` 自動寫入，見 BP-UI-1）。

`execute()`：`lora_data`（JSON）優先於單一 `lora_1` widget 組成最終 LoRA 清單；若
`save_as_profile` 非空，計算存檔路徑（`checkpoint` 檔名去副檔名作子資料夾，除非
`output_name`/儲存路徑以 `/` 開頭）、從當前 workflow 圖中找 `title == "note"` 且
`type == "CLIPTextEncode"` 的節點取值存入 `note` 欄位，寫出 profile JSON
（`nodes/image/factory/profile_factory.py:67-103`）。

### Manager 載入邏輯

`INPUT_TYPES` 動態列出 `get_storage_path()` 下所有 `.json`（遞迴子資料夾，相對路徑作 id）。
`load()` 相容兩種 profile 格式：新版分類欄位（`character`/`H`/`expression`/`pose`/`scene`）與
舊版單一 `positive` 字串（向後相容判斷：`has_new = any(k in data for k in new_keys)`）。

### 輸出檔名模板（`process_output_name`）

`output_name` 支援 `%NodeTitle.field%` / `%NodeId.field%` 模板語法,在執行時從當前 prompt 圖
即時取值（例：`%KSampler.seed%` 取該節點 `seed` 輸入的當前值；`.field` 含 `seed` 時額外
容錯查 `noise_seed`）。除非模板以 `/` 開頭，否則自動在最前面加上 `{checkpoint 檔名去副檔名}/`
前綴（對應原始需求：`output_name = 角色分類/角色名字_%Seed.seed%` →
`qweasdV123/角色分類/角色名字_%Seed.seed%`）。最終路徑再統一加 `images/` 前綴
（2026-02-15，`a78cd58`）。

### Profile 儲存位置（刻意置於外部）

`get_storage_path()` 回傳 `<plugin_root>/../../user/default/misaka-prompt-sets`——
ComfyUI 的 `user/default/` 目錄下，刻意與外掛程式碼分開存放（對應原始需求「我希望這個node存的
資料會在外部...而不是跟node程式碼放在一起」）。

## 存/讀流程（含路徑防護現況）

```mermaid
sequenceDiagram
    participant U as 使用者
    participant JS as image_factory.js
    participant API as /misaka/save_profile,/load_profile
    participant Node as ProfileFactory.execute() / PromptManager.load()
    participant FS as misaka-prompt-sets/

    Note over U,JS: 存檔路徑 A（REST，UI 存檔按鈕）
    U->>JS: 點「Save Profile (No Run)」
    JS->>API: POST /misaka/save_profile {filename, data}
    API->>API: resolve_profile_path()（cab4ac0 已修復，拒絕逃逸 base）
    API->>FS: 寫入 json

    Note over U,Node: 存檔路徑 B（節點執行時的 save_as_profile widget）
    U->>Node: Queue（save_as_profile 非空）
    Node->>Node: resolve_profile_path()（2026-07-22 commit 3ce3b4a 已修復，拒絕逃逸 base）
    Node->>FS: 寫入 json

    Note over U,Node: 讀取路徑（PromptManager，已修復）
    U->>Node: Queue（選定 profile）
    Node->>Node: resolve_profile_path()（cab4ac0 已修復）
    Node->>FS: 讀取 json
```

## 已修復（2026-07-22，commit 3ce3b4a）

`MisakaImageProfileFactory.execute()` 的 `save_as_profile` 存檔路徑
（原 `nodes/image/factory/profile_factory.py:73`）曾用 `os.path.join(base_path, save_as_profile.strip() + ".json")`
直接組路徑,**沒有呼叫** `resolve_profile_path()`——這與 `cab4ac0`（2026-06-20）修的
REST `/misaka/save_profile` 路由、`MisakaImagePromptManager.load()` 不同（見 BP-API-1）。
ComfyUI 的執行 API（`POST /prompt`）接受完整 workflow JSON（含 widget 值）,任何呼叫者理論上
可送出一個把 `save_as_profile` 設為 `../../../xxx` 的 graph,透過此節點的 `execute()` 寫檔到
storage root 之外——REST 路由的修復當時未覆蓋這條路徑。

**修復**：`execute()` 改用與路由/Manager 相同的 `resolve_profile_path(base_path, save_as_profile.strip())`
計算存檔路徑,拒絕（`ValueError`）時走既有 `except Exception` 分支（記錄 log、不寫檔),
行為與 REST 路由一致。先以 `tests/test_path_traversal.py::test_node_save_traversal_rejected`
在修復前跑出 RED（`'../escaped'` 確實逃逸至 storage root 外),修復後轉 PASS,並新增
`test_node_save_normal_name_still_saves` 覆蓋一般名稱仍可正常存檔的迴歸(見 `tests` 欄位)。
