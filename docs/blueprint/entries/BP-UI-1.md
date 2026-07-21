---
id: BP-UI-1
title: Profile Factory 前端動態 UI（動態 LoRA 欄位 / 篩選器 / 存讀按鈕 / note 同步）
system: ui
tags: [js, litegraph, dynamic-widgets, lora]
status: 已完成
request_verbatim: >-
  「lora可能會需要串接多個，也要保留原是的strenth model & clip參數」「custom output point要有:
  MODEL, CLIP, VAE, TEXT」（repo root `prompt` 檔案第 1 行需求的 UI 落實部分；資料夾篩選/存讀
  按鈕/note 同步為 2026-01-26 三個 commit 訊息記錄的後續迭代，無獨立逐字稿）
decided_date: 2026-01-25
exec_links:
  - js/image_factory.js
  - nodes/image/factory/profile_factory.py（save_as_profile / lora_data / node_map 消費端，見 BP-IMG-1）
  - nodes/image/factory/prompt_manager.py
done_date: 2026-06-20
revisions:
  - date: 2026-01-26
    summary: "commit 5ff89dc — 存檔按鈕 + 資料夾篩選選單（Folder Filter 1/2）+ README"
  - date: 2026-01-26
    summary: "commit e1ddedc — note 欄位存/讀同步（尋找 workflow 中 title=\"note\" 的 CLIPTextEncode 節點）+ LoRA 選擇器連動邏輯"
  - date: 2026-01-26
    summary: "commit 54883b4 — 存/讀 profile 的 UX 調整"
  - date: 2026-06-20
    summary: "commit 1c38b84 — README 補充節點清單與資安警示（間接反映此 UI 涵蓋範圍已定形，無程式碼變動）"
origin: "prompt（repo root，需求逐字稿第 1 行）+ 三個 2026-01-26 commit 訊息"
---

## 設計說明

`js/image_factory.js`（ComfyUI `app.registerExtension`,`beforeRegisterNodeDef` hook）
為 `MisakaImageProfileFactory`/`MisakaImagePromptManager`/`MisakaImagePromptBuilder`
三個節點提供純前端的動態互動,伺服器端節點本身只認得固定 widget（見 BP-IMG-1/2）。

### 動態 LoRA 欄位（Factory）

`addLoraGroup(index)`/`removeLoraGroupsFrom(startIndex)`：每個 `lora_N` combo widget 掛
callback,選了非 `None` 的 LoRA 就自動長出下一組 `lora_{N+1}` + 對應 `strength_model`/
`strength_clip`（對應原始需求「lora可能會需要串接多個，也要保留原是的strenth model & clip
參數」）；改回 `None` 則自動裁掉之後的空組。`onSerialize` 時把所有已填 LoRA 序列化進隱藏欄位
`lora_data`（JSON array）,伺服器端 `execute()` 優先讀這個欄位（見 BP-IMG-1）。

### Profile 選擇器 + 兩層資料夾篩選

`refreshFileList()` 拉 `/misaka/profile_list`,`updateFilters()`/`updateSelector()` 依
`Folder Filter 1`/`Folter Filter 2` 兩層下拉即時過濾候選清單（避免上百個 profile 時选单太長）。
`syncSaveAsFilename()`（「Overwrite Filename」按鈕）把選中 profile 名稱去掉 checkpoint stem
前綴後填回 `save_as_profile`,方便「載入後改一點再存回同名檔」的工作流。

### 存 / 讀按鈕

「Save Profile (No Run)」：收集所有 widget 值 + note 節點內容,`POST /misaka/save_profile`
（見 BP-API-1）。「Load Profile」：`GET /misaka/load_profile?name=...`,把回傳資料寫回對應
widget,並依 `loras` 陣列長度動態 `addLoraGroup()` 補足欄位數。

### note 欄位雙向同步

存檔時掃描 `app.graph._nodes` 找 `title === "note" && type === "CLIPTextEncode"` 的節點,
把其 widget 值寫進 profile 的 `note` 欄位；載入時反向寫回該節點（對應 BP-IMG-1 body 的
「note 欄位」設計）。

### 隱藏輔助欄位

`node_map`/`lora_data`/`prompt_data` 三個 widget 用 `hideMisakaWidgets()` 隱藏（`type =
"hidden"`,`computeSize` 回傳 `[0,-4]`）——這些欄位只給伺服器端 `execute()` 消費,不需要
使用者直接編輯。
