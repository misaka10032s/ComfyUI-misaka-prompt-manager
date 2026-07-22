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

> 以下各節為 `docs/superpowers/specs/SPEC-voice-conversion.md`（已移除，見
> `docs/blueprint/MIGRATION.md` §1）對應章節的逐字照抄；PM 撰寫的說明移至文末
> 「補充（非原文）」。

## 依賴套件（requirements 新增）

```
# 即時音訊串流
sounddevice>=0.4.6       # 跨平台麥克風 / 喇叭 API
```

### `voice/realtime_stream.py`

**功能**：麥克風 → RVC → 喇叭的即時串流，設計為獨立 process（`multiprocessing.Process`）。

```python
class RealtimeVCStream:
    def __init__(
        self,
        converter: RVCConverter,
        input_device: int | None = None,   # None = 系統預設麥克風
        output_device: int | None = None,  # None = 系統預設喇叭
        block_time_ms: int = 250,          # 每次處理音訊長度
        extra_context_ms: int = 2500,      # 前後 overlap 防 artifacts
        crossfade_ms: int = 50,
        f0_method: str = "rmvpe",          # 即時建議 rmvpe（比 harvest 快）
    ): ...

    def start(self): ...   # 啟動串流（非阻塞，背景執行）
    def stop(self): ...    # 停止串流
    def is_running(self) -> bool: ...

    @staticmethod
    def list_devices() -> list[dict]:
        """列出可用音訊裝置，供 ComfyUI 節點下拉選單使用。"""
```

**緩衝區設計**（環形 buffer）：
```
[─────────── extra_context ───────────][─ block ─][─ extra_context ─]
        ↑ 前次 overlap                               ↑ 後次 overlap
                              ↑ 實際輸出區段
```
每次只輸出中間 `block_time` 的部分，前後 extra_context 用來提升音質。

## ComfyUI 節點規格（`voice_nodes.py`）

### Node 4：`MisakaVCRealtimeStart` 〔未實作 — 藍圖〕

**用途**：啟動即時 VC 串流（非阻塞，後台執行）。
*目前狀態：未實作為 ComfyUI 節點（見本節開頭實作狀態說明）。*

```python
INPUT_TYPES:
  required:
    vc_model:        VC_MODEL
    input_device:    COMBO   （由 list_devices() 動態生成）
    output_device:   COMBO   （由 list_devices() 動態生成）
  optional:
    vc_params:       VC_PARAMS
    block_time_ms:   INT    default=250, min=50,  max=1000
    extra_context_ms:INT    default=2500,min=500, max=5000
    f0_up_key:       INT    default=0,   min=-12, max=12
    f0_method:       COMBO  ["rmvpe", "harvest", "crepe"]  default="rmvpe"

RETURN_TYPES:  ("VC_STREAM", "STRING")
RETURN_NAMES: ("stream_handle", "status")
```

### Node 5：`MisakaVCRealtimeStop` 〔未實作 — 藍圖〕

**用途**：停止即時 VC 串流。
*目前狀態：未實作為 ComfyUI 節點（見本節開頭實作狀態說明）。*

```python
INPUT_TYPES:
  required:
    stream_handle: VC_STREAM

RETURN_TYPES:  ("STRING",)
RETURN_NAMES: ("status",)
```

## 型別定義

```python
# voice 型別（需在 NODE_CLASS_MAPPINGS 旁邊定義）
# ComfyUI 識別自訂型別的方式：RETURN_TYPES 中用大寫字串即可，
# 不需額外宣告，只要收發節點用相同字串就會自動連線。

# VC_STREAM → RealtimeVCStream 實例
```

## 即時 VC 與未來擴充（臉部轉換）的隔離設計

即時 VC 串流以 `multiprocessing.Process` 跑在獨立 process：

```
主 process（ComfyUI）
  → spawn RealtimeVCStream process（音訊）
  → spawn [Future] FaceConversion process（影像）
  兩者透過 multiprocessing.Queue 各自獨立，互不阻塞
```

`MisakaVCRealtimeStart` 回傳的 `VC_STREAM` 是 handle（含 PID + Queue），
`MisakaVCRealtimeStop` 透過 handle 送停止信號再 join process。

## 實作注意事項

3. **執行緒安全**：`MisakaVCRealtimeStart` 的 stream handle 要用 `threading.Lock` 保護狀態，避免重複啟動。

## 補充（非原文）

> 以下為 PM 於遷移時撰寫的說明性內容（非 SPEC 原文），移到此處保留，不併入上方逐字段落。

### 設計說明

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

### 待判斷（需使用者裁定去留）

`.claude/CLAUDE.md` 已明文列為待決：**保留（補完節點包裝後交付）或移除（含底層引擎一併
`git rm`）**——兩個方向都合理,取決於是否仍有即時語音轉換的實際需求。在使用者裁定前,
本條目狀態維持「待判斷」,底層引擎程式碼保留不動。
