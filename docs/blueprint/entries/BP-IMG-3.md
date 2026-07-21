---
id: BP-IMG-3
title: Loop Ckpt × Loop Prompt 跨 Checkpoint × Prompt 交叉生圖
system: img
tags: [loop, cross-product, checkpoint, prompt, batch]
status: 已完成
request_verbatim: >-
  「新增 checkpoint × prompt 交叉循環生圖節點」（git commit message 逐字，原始需求未見於
  `prompt` 逐字稿檔——此功能為該檔案記錄範圍之後新增,以 commit message 作為現存最早可證明來源）
decided_date: 2026-05-13
exec_links:
  - nodes/image/loop/_state.py
  - nodes/image/loop/ckpt_input.py
  - nodes/image/loop/prompt_input.py
  - nodes/image/loop/loop_ckpt_core.py
  - nodes/image/loop/loop_prompt_core.py
  - nodes/image/loop/loop_manager.py
  - js/image_loop.js（前端動態輸入槽，見 BP-UI-2）
  - README.md#6-7（僅描述早期簡化版介面，見「README 現況落差」）
done_date: 2026-06-08
revisions:
  - date: 2026-05-13
    summary: "commit 1d6ffae — 初版 MisakaLoopCkpt / MisakaLoopPrompt：Ckpt 節點直接輸出 MODEL/CLIP/VAE/ckpt_name/run_info，Prompt 節點取代 CLIP Text Encode，兩者為單一節點，透過 module-level 計數器循環（每次 Queue 換一組 ckpt×prompt 組合）"
  - date: 2026-05-13
    summary: "commit 443c647 — 支援 %NodeTitle.field% prompt 模板解析（後併入 _state.py:_resolve_prompt_templates）"
  - date: 2026-05-24
    summary: "commit a4ebc12 — 重構支援 solo 模式（無 CkptCore 時 PromptCore 仍可獨立循環）、run_info 準確度、UX 清理"
  - date: 2026-05-24
    summary: "commit b13acaa — 拆分為 nodes/image/loop/ 套件；原「一體式」節點拆成 MisakaLoopCkpt/MisakaLoopPrompt（UI 選擇器,純傳值)+ MisakaLoopCkptCore/MisakaLoopPromptCore（實際載入/編碼)。此為架構轉折點——README 現有文字仍描述拆分前的簡化行為，未同步更新（見下方落差說明）"
  - date: 2026-05-24
    summary: "commit 285e1d5 — 修正 auto-grow 動態輸入槽只套用在 Core 節點（不是選擇器節點）"
  - date: 2026-05-25
    summary: "commit e0df02c — MisakaLoopPromptCore 支援多維度（multi-dimension）cross-product：可放置多個 PromptCore 節點各自代表一個獨立維度，總次數 = N_ckpt × dim1 × dim2 × …"
  - date: 2026-06-07
    summary: "commit 854ada1 — 新增 MisakaLoopManager 節點統一組裝最終路徑；CkptCore/PromptCore 移除 dimension/base_folder 參數（改由 Manager 統一負責）"
  - date: 2026-06-08
    summary: "commit 1edd72d — MisakaLoopManager 定形：讀取 conditioning_N 插槽連線圖反查來源節點,依插槽順序組裝路徑段"
origin: "git commit 1d6ffae 訊息（無先於此的逐字需求文件）"
---

## 設計說明

在同一次「Queue」批次中,自動輪替不同 checkpoint × 不同 prompt 的組合生成圖片,取代手動
逐一切換 checkpoint/prompt 重複執行的流程。目前為**五個節點的組合架構**（README 僅記載較早的
簡化版兩節點介面,見下方落差說明）：

| 節點 | 角色 | 輸出 |
|---|---|---|
| `MisakaLoopCkpt` | UI 選擇器：checkpoint 下拉,原樣傳出字串 | `ckpt_name` (STRING) |
| `MisakaLoopPrompt` | UI 選擇器：`alias` + `text` 包成一個 wire | `MISAKA_PROMPT` (alias, text) |
| `MisakaLoopCkptCore` | 實際執行：接收多個 `ckpt_name_N`（動態插槽,見 BP-UI-2）,依當前 run index 選一個載入 | `MODEL`/`CLIP`/`VAE` |
| `MisakaLoopPromptCore` | 實際執行：接收多個 `prompt_N`（動態插槽）,依當前 run index 選一個並編碼 | `CONDITIONING` |
| `MisakaLoopManager` | 組裝最終輸出路徑 + 執行進度字串 | `formatted_name`/`run_info` |

### 狀態機（`_state.py:_LoopState`，module-level singleton，`threading.Lock` 保護）

- `run_index`/`current_run`：全域執行計數器,每次 `CkptCore.execute()` 時 `% total` 遞增。
- Ckpt 為**最外層（最慢）維度**；每個 `PromptCore` 節點透過 `unique_id` 作為獨立
  維度 key,寬度（連了幾個 `prompt_N`）寫入 `dim_sizes_next`,下次 `CkptCore` 執行時「promote」
  成 `dim_sizes`（pending/committed 兩階段,避免刪除某個 `PromptCore` 節點後殘留過期維度）。
- 總執行次數 = `N_ckpts × dim_size_1 × dim_size_2 × …`；index 計算用「里程表」演算法
  （outermost=ckpt,越後加入的維度循環越快）。
- 無 `CkptCore`（solo 模式）時,`PromptCore` 自己用 `solo_indices` 循環,不受 ckpt 維度影響。

### 交叉生圖流程

```mermaid
flowchart TD
    A["每個 checkpoint 接一個 MisakaLoopCkpt<br/>全部連到 MisakaLoopCkptCore"] --> C
    B["每組 prompt 接一個 MisakaLoopPrompt<br/>全部連到 MisakaLoopPromptCore（可多組 Core = 多維度）"] --> D
    C["MisakaLoopCkptCore.execute()<br/>promote dim_sizes_next → dim_sizes<br/>計算 run_index % total → ckpt_idx + dim_indices"] --> E["載入 checkpoint<br/>輸出 MODEL/CLIP/VAE"]
    D["MisakaLoopPromptCore.execute()<br/>依 unique_id 查 dim_indices 取 idx<br/>編碼對應 prompt"] --> F["輸出 CONDITIONING"]
    E --> G["MisakaLoopManager.execute()<br/>反查 conditioning_N 連線圖,依插槽序組裝路徑"]
    F --> G
    G --> H["formatted_name = base_folder/alias1/alias2/.../ckpt_stem<br/>run_info = 'ckpt i/N  prompt j/M  run k/total'"]
    H --> I["接 SaveImage 的 filename_prefix"]
    I --> J["ComfyUI Batch count = 總組合數,按一次 Queue"]
```

`reset_counter`（`MisakaLoopManager`）：勾選後下次執行時把 `run_index` 歸零,從第一個組合
重新開始。`IS_CHANGED` 回傳 `float("nan")` 讓這幾個節點每次 Queue 都強制重新執行（不被
ComfyUI 的快取機制跳過）。

## README 現況落差（誠實記錄）

`README.md` 第 6/7 節（EN/zh-TW/日本語三處皆同）描述的是 **2026-05-13 到 2026-05-24
之間的簡化版介面**：`Misaka Loop Ckpt` 直接輸出 `MODEL`/`CLIP`/`VAE`/`ckpt_name`/`run_info`,
`Misaka Loop Prompt` 直接輸出 `CONDITIONING`/`formatted_name`。`b13acaa`（2026-05-24）拆分為
上表五節點架構後,README 未同步更新——目前 `MisakaLoopCkpt`/`MisakaLoopPrompt` 只是把值原樣
傳出的 UI 選擇器,真正的載入/編碼/路徑組裝邏輯在 `*Core` 與 `MisakaLoopManager`。此落差已在
`@PM` registry `ComfyUI-misaka-prompt-manager.md` 記錄為待補項目,本條目記錄設計現況以此
blueprint 為準。
