---
id: BP-IMG-4
title: Scale Preset / Scale Custom（解析度輔助節點）
system: img
tags: [resolution, scale, upscale, sdxl]
status: 已完成
request_verbatim: >-
  「voice tts new node」（git commit 33ff949 訊息；本次同一 commit 一併新增 image_nodes.py
  的解析度輔助節點，無獨立逐字需求文件——以 commit message 作為現存最早可證明來源）
decided_date: 2026-04-20
exec_links:
  - nodes/image/scale/_shared.py
  - nodes/image/scale/preset.py
  - nodes/image/scale/custom.py
  - js/image_scale.js（前端 Calculate 按鈕，見 BP-UI-3）
  - README.md#8
done_date: 2026-05-24
revisions:
  - date: 2026-04-20
    summary: "commit 33ff949 — 新增 MisakaScalePreset / MisakaScaleCustom（image_nodes.py）"
  - date: 2026-05-24
    summary: "commit b13acaa — 拆分為 nodes/image/scale/ 套件（preset.py/custom.py/_shared.py）"
origin: "git commit 33ff949 訊息"
---

## 設計說明

兩個獨立的解析度輔助節點（分類 `MisakaNodes`,不屬於 `MisakaNodes/Image`）,輸出
`width`/`height`/`scaled_width`/`scaled_height`/`info`,方便接到 `EmptyLatentImage`（原始尺寸）
與放大節點（`×scale` 尺寸）,兩者都把結果對齊 8 的倍數（`_round8()`）。

### Misaka Scale Preset

從 `_SCALE_PRESETS` 精選清單（SD1.5：9 組 ~512K px；SDXL/Pony：9 組 ~1M px,例如
`832×1216 (2:3 XL)`）下拉挑選 + `scale`（1.0–8.0）,`_parse_preset()` 用正規表達式解析
`寬×高` 部分,回傳原始尺寸與 `×scale` 後尺寸。

### Misaka Scale Custom

`aspect_ratio`（14 組常見比例 + `free`）+ `width`/`height` + `scale`。邏輯
（`nodes/image/scale/custom.py:execute`）：
- `aspect_ratio != "free"` 且恰有一邊為 `0` → 依比例算出另一邊（`_round8()`）。
- 兩邊都 `>0` → 視為已由前端「Calculate」按鈕解出（見 BP-UI-3),直接使用。
- 兩邊都 `0` → 丟 `ValueError`,提示先按 Calculate 或至少填一邊。

`scale` 套用同一邏輯產生放大後尺寸,`info` 字串附上目前比例標籤方便核對。
