---
id: BP-UI-4
title: Voice 節點檔案挑選器（音訊上傳 + RVC 模型/index 瀏覽）
system: ui
tags: [js, litegraph, file-picker, rvc]
status: 已完成
request_verbatim: >-
  「修正結構 — 分開 image新增 audio + video 類別的node」（git commit 56444c8 訊息，同一 commit
  新增語音節點群，見 BP-VOICE-1；檔案挑選器 UI 本身無獨立逐字需求文件）
decided_date: 2026-04-17
exec_links:
  - js/voice.js
  - __init__.py（/misaka/rvc_model_list /misaka/rvc_index_list，見 BP-API-1）
  - ComfyUI 內建 /upload/image 端點（音訊檔上傳，非本外掛新增）
done_date: 2026-05-24
revisions:
  - date: 2026-04-17
    summary: "commit 56444c8 — 語音節點群初版，含最初的檔案挑選 UI"
  - date: 2026-05-24
    summary: "commit b13acaa — 拆分為獨立 js/voice.js"
origin: "git commit 56444c8 訊息"
---

## 設計說明

語音節點的 `STRING` 路徑欄位（`audio_path`/`reference_audio`/`model_path`/`index_path`）
提供兩種前端檔案挑選器,避免使用者手動輸入完整路徑：

### 一般音訊上傳（`MisakaVCConvertBatch`/`MisakaVCAudioInfo`/`MisakaVCAutoParams`/
`MisakaVCPMGenerate`）

`_addFilePicker()` 加一顆「choose file to upload」按鈕,開瀏覽器原生檔案選擇對話框,選定檔案
後透過 ComfyUI 內建的 `POST /upload/image` 端點上傳（`type: "input"`,即使是音訊檔也走這個
既有端點),回傳的檔名寫回對應 widget。接受 `.wav/.mp3/.flac/.ogg/.m4a/.aac`。

### RVC 模型/index 瀏覽器（`MisakaVCLoadModel`）

不透過上傳（`.pth`/`.index` 檔案應已放在 `ComfyUI/models/rvc/`),而是「📂 Browse」按鈕打
`GET /misaka/rvc_model_list` / `/misaka/rvc_index_list`（見 BP-API-1,回傳伺服器上既有檔案
清單),彈出一個自繪的 overlay 選單列出所有找到的檔案供點選,`index_path` 額外提供「(空 / 不使用
index)」選項對應「可選不接 index」的設計。找不到任何檔案時提示使用者放檔案的正確路徑。
