---
id: BP-UI-3
title: Scale Custom「Calculate」按鈕
system: ui
tags: [js, litegraph, aspect-ratio]
status: 已完成
request_verbatim: >-
  「voice tts new node」（git commit 33ff949 訊息，同一 commit 新增 Scale 節點群，見 BP-IMG-4；
  Calculate 按鈕本身無獨立逐字需求文件，以最早引入 Scale 節點的 commit 訊息作為來源）
decided_date: 2026-04-20
exec_links:
  - js/image_scale.js
  - nodes/image/scale/custom.py（伺服器端二次驗證同一比例邏輯，見 BP-IMG-4）
done_date: 2026-05-24
revisions:
  - date: 2026-04-20
    summary: "commit 33ff949 — 隨 MisakaScaleCustom 節點一併新增 Calculate 按鈕（misaka_dynamic.js）"
  - date: 2026-05-24
    summary: "commit b13acaa — 隨節點拆分移到獨立 js/image_scale.js"
origin: "git commit 33ff949 訊息"
---

## 設計說明

`MisakaScaleCustom` 的 `width`/`height` 其中一邊可能是 `0`（表示「依比例推算」）,但 Python
節點的 `execute()` 只在恰好一邊為 0 時才會推算(見 BP-IMG-4)——若使用者想先在 UI 上看到算好
的結果、或兩邊都想手動指定後再依比例對齊高度,需要一個前端即算的入口。

`js/image_scale.js` 加一顆「Calculate」按鈕：讀目前 `aspect_ratio`/`width`/`height` widget
值,`aspect_ratio !== "free"` 時依比例算出另一邊（`snap8()` 對齊 8 的倍數,與伺服器端
`_round8()` 邏輯一致）——寬優先：若兩邊都 `>0`,以 `width` 為準重算 `height`。純前端運算,
不觸發節點執行,方便使用者在按下 Queue 前先確認尺寸。
