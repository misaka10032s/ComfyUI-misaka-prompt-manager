---
id: BP-VOICE-3
title: 即時麥克風↔喇叭語音轉換（Realtime VC）
system: voice
tags: [rvc, realtime, streaming, unregistered]
status: 待判斷
request_verbatim: >-
  voice/realtime_stream.py # 麥克風 ↔ 喇叭即時串流（藍圖引擎，尚未接成節點）
  （docs/superpowers/specs/SPEC-voice-conversion.md 目錄結構段原文；同檔案「實作狀態（2026-06）」
  段落明文：「Node 4/5 即時串流...尚未實作為 ComfyUI 節點...底層引擎已存在，但沒有對應的節點類別、
  VC_STREAM 型別串接或 JS 裝置列舉支援」）
decided_date: 2026-04-17
exec_links:
  - docs/superpowers/specs/SPEC-voice-conversion.md#node-4-misakavcrealtimestart-未實作—藍圖
  - docs/superpowers/specs/SPEC-voice-conversion.md#node-5-misakavcrealtimestop-未實作—藍圖
  - voice/realtime_stream.py
  - .claude/CLAUDE.md（"Realtime streaming nodes...NOT registered...do not delete without checking the roadmap task first"）
revisions:
  - date: 2026-04-17
    summary: "commit 56444c8 — MisakaVCRealtimeStart/Stop 類別隨 voice_nodes.py 一併寫入（原始 398 行版本），但從未加入該次 commit 的 NODE_CLASS_MAPPINGS——即從第一個相關 commit 起就是「已寫程式碼、未註冊」的狀態"
  - date: 2026-06-20
    summary: "commit a81a7f2 — SPEC-voice-conversion.md 明確補註「實作狀態（2026-06）」段落，誠實標記此為未交付功能、保留為待辦藍圖，避免文件誤導成已完成"
origin: "docs/superpowers/specs/SPEC-voice-conversion.md Node 4/5 段落"
---

## 設計說明

麥克風 → RVC → 喇叭的即時語音轉換串流,設計為獨立 process（`multiprocessing.Process`),
不阻塞 ComfyUI 主流程。底層引擎 `voice/realtime_stream.py:RealtimeVCStream` 存在且完整
（`start()`/`stop()`/`is_running()`/`list_devices()` 皆已實作,環形 buffer 設計含
`extra_context_ms` overlap 防 artifacts、`crossfade_ms` 拼接),但**從未被包裝成 ComfyUI 節點**：

- 沒有對應的 `MisakaVCRealtimeStart`/`MisakaVCRealtimeStop` 節點類別出現在任何一版
  `NODE_CLASS_MAPPINGS`（`nodes/voice/__init__.py` 目前只匯出 5 個節點,不含這兩個）。
- 規格中定義的 `VC_STREAM` 自訂型別（串接 handle,含 PID + Queue）未被任何節點使用。
- 前端裝置列舉（`list_devices()` 供下拉選單用）沒有對應的 JS UI 支援。

### 規劃中的節點介面（設計藍圖,未交付）

`MisakaVCRealtimeStart`：`vc_model`/`input_device`/`output_device`（`COMBO`,由
`list_devices()` 動態生成）+ `block_time_ms`/`extra_context_ms`/`f0_up_key`/`f0_method`,
輸出 `VC_STREAM` + 狀態文字。`MisakaVCRealtimeStop`：接收 `VC_STREAM`,送停止信號並
`join()` process。完整參數規格見 `SPEC-voice-conversion.md` Node 4/5 段。

## 待判斷（需使用者裁定去留）

`.claude/CLAUDE.md` 已明文列為待決：**保留（補完節點包裝後交付）或移除（含底層引擎一併
`git rm`）**——兩個方向都合理,取決於是否仍有即時語音轉換的實際需求。在使用者裁定前,
本條目狀態維持「待判斷」,底層引擎程式碼保留不動。
