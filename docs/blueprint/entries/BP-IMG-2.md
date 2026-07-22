---
id: BP-IMG-2
title: Prompt Builder（多段動態串接）
system: img
tags: [prompt, conditioning, concat]
status: 已完成
request_verbatim: >-
  「現在我想知道能不能把多個prompts組合起來一個node自動concat，變成有多個輸入框在同一個node
  block，還可以靈活增減輸入框數量，然後把這些prompts concat起來成為最終的prompt輸出到
  KSampler，他的input 是CLIP, output是CONDITIONING」
  （逐字稿見 repo root `prompt` 檔案第 22 行）
decided_date: 2026-01-25
exec_links:
  - prompt（原始需求逐字稿，repo root，第 22 行）
  - nodes/image/factory/prompt_builder.py
done_date: 2026-05-24
revisions:
  - date: 2026-07-22
    summary: "[blueprint 日期回填，fresh reviewer 發現缺 done_date] git log --follow nodes/image/factory/prompt_builder.py 只有一個 commit：b13acaa（2026-05-24，單體檔案拆分為 nodes/ 套件）。逐行比對 b13acaa 拆分前後的 execute()/INPUT_TYPES 邏輯（含 a35f5e7 2026-01-25 init 版本），確認功能自 init 起即完整、無任何行為變更——b13acaa 只把類別搬到獨立檔案、CATEGORY 由 \"MisakaNodes\" 改成 \"MisakaNodes/Image\"，非功能性修改。無法找到 init 之後任何『完成』里程碑 commit（因為功能在 init 當下即已完整）；依既有慣例（BP-IMG-4 對同一 commit 的用法一致）以 b13acaa 作為可考的 done_date 出處"
origin: "prompt（repo root，需求逐字稿）"
---

## 設計說明

模組化 prompt 串接節點——取代原先「一次只能一個字串 prompt」的限制。`clip` + `text_1`
為必填，額外段落透過前端動態新增文字框（見 BP-UI-1 的 `text_N` 自動增減邏輯,序列化進隱藏欄位
`prompt_data` JSON array）。

`execute()`（`nodes/image/factory/prompt_builder.py`）：
1. 若有 `conditioning_in` 接入,作為串接起點（可接在其他 conditioning 節點之後）。
2. `text_1` 非空 → tokenize + encode，與起點沿 tensor dim=1 串接（`concat_cond()`：兩個
   conditioning 的 pooled tensor 若 batch 維度一致才串接，否則印警告並保留原值）。
3. 解析 `prompt_data`（JSON 字串陣列，由前端序列化,見 BP-UI-1）,逐一 encode 並串接。
4. 全部為空時 fallback 為空字串的 encode 結果（避免下游節點收到 `None`）。

輸出單一 `CONDITIONING`,可直接接 `KSampler` 的 positive/negative 輸入,對應原始需求
「input 是CLIP, output是CONDITIONING」。

> **完成時點無獨立紀錄**（與 `a35f5e7`〔2026-01-25 init〕同批——功能自第一個 commit 起即完整,
> 之後唯一觸及此檔的 `b13acaa`〔2026-05-24〕僅為套件拆分,無行為變更,見下方 revisions 逐行
> 比對記錄）。

