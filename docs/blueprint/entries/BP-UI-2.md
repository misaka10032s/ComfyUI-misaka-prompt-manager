---
id: BP-UI-2
title: Loop 節點動態輸入槽（auto-grow / auto-trim）
system: ui
tags: [js, litegraph, dynamic-widgets, loop]
status: 已完成
request_verbatim: >-
  「fix: apply auto-grow input slots to Core nodes, not input helpers」（git commit 285e1d5
  訊息；此 UI 機制服務 BP-IMG-3 的多節點交叉生圖架構，無獨立逐字需求文件）
decided_date: 2026-05-24
exec_links:
  - js/image_loop.js
  - nodes/image/loop/loop_ckpt_core.py（消費 ckpt_name_N，見 BP-IMG-3）
  - nodes/image/loop/loop_prompt_core.py（消費 prompt_N）
  - nodes/image/loop/loop_manager.py（消費 conditioning_N）
done_date: 2026-05-24
revisions:
  - date: 2026-05-24
    summary: "commit 285e1d5 — 修正自動增減輸入槽只套用在 MisakaLoopCkptCore/MisakaLoopPromptCore/MisakaLoopManager（Core/Manager），不是純傳值的 MisakaLoopCkpt/MisakaLoopPrompt 選擇器節點"
origin: "git commit 285e1d5 訊息"
---

## 設計說明

`js/image_loop.js` 為 `MisakaLoopCkptCore`（插槽前綴 `ckpt_name`,型別 `STRING`）、
`MisakaLoopPromptCore`（`prompt`,型別 `MISAKA_PROMPT`）、`MisakaLoopManager`
（`conditioning`,型別 `CONDITIONING`）三個節點提供統一的動態輸入槽邏輯,取代使用者手動
一個一個加減輸入端口。

- `_grow(node)`：掃描目前 `{prefix}_N` 最大編號,若最後一個插槽已連線就自動加一個
  `{prefix}_{N+1}` 空插槽（`onNodeCreated`/`onConfigure`/`onConnectionsChange` 皆會觸發)。
- `_trim(node)`：斷開連線時,只有「最後一格與其前一格都空」才真正移除最後一格（保留至少
  1 格),避免移除中間某條連線時誤刪其他已連線插槽（例：`prompt_5` 斷線,只要 `prompt_1..4`
  仍連著,不會把 `prompt_1..4` 動到）。

此機制讓 BP-IMG-3 的交叉生圖架構可以在畫面上直接「接上第 N 個 checkpoint / prompt / 維度」,
不需要重新產生節點或手動改參數。
