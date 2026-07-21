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
