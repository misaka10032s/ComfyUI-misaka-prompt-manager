# Misaka Voice Conversion — 實作規格書

本文件描述新增至 `ComfyUI-misaka-prompt-manager` 的語音轉換模組。
實作時應遵循現有 `misaka_node.py` 的 ComfyUI 節點風格（`INPUT_TYPES` / `RETURN_TYPES` / `FUNCTION` / `CATEGORY = "MisakaNodes/Voice"`）。

---

## 目錄結構（新增部分）

```
ComfyUI-misaka-prompt-manager/
  voice/                   # 底層引擎（非 ComfyUI 節點）
    __init__.py
    resampler.py           # 高品質重採樣（soxr）
    auto_params.py         # 自動判斷 RVC 參數
    rvc_wrapper.py         # RVC 推理封裝；convert() 內建靜音切點分段 + overlap
    realtime_stream.py     # 麥克風 ↔ 喇叭即時串流（藍圖引擎，尚未接成節點）
  nodes/voice/             # 實際 ComfyUI 節點實作（取代原規劃的 voice_nodes.py）
    load_model.py / auto_params.py / convert_batch.py / audio_info.py / pm_generate.py
```

> **與原規格差異（誠實註記）**：
> - 原規劃的 `segmentation.py`（`find_cut_points`）與 `crossfade.py`（`concat_with_crossfade`）
>   為獨立的靜音分段／拼接實作，但從未被任何節點使用 —— `RVCConverter.convert()` 已內建
>   等效的 Ultimate-RVC 靜音切點分段與 overlap 處理，故這兩個檔案已移除（死碼）。
> - 節點實作位於 `nodes/voice/`，不存在獨立的 `voice_nodes.py`。`NODE_CLASS_MAPPINGS`
>   由 `nodes/voice/__init__.py` 匯出並併入外掛根 `__init__.py` 的主對應表。

---

## 依賴套件（requirements 新增）

```
# 音訊處理
librosa>=0.10.0          # 靜音偵測、頻譜分析
soundfile>=0.12.1        # WAV 讀寫
soxr>=0.3.7              # 高品質重採樣（比 scipy 快且無 aliasing）
numpy>=1.26.0

# 即時音訊串流
sounddevice>=0.4.6       # 跨平台麥克風 / 喇叭 API

# RVC 依賴（需使用者自行安裝 RVC 環境）
# faiss-gpu              # 向量索引（RVC .index 搜尋）
# torchcrepe             # F0 基頻偵測
# pyworld                # WORLD 聲碼器（harvest F0）

# 可選：品質評估
pesq>=0.0.4              # 語音品質感知分數（用於 auto_params）
```

---

## 核心模組規格

### `voice/segmentation.py` 〔已移除 — 死碼〕

> 未被任何節點使用；等效分段已內建於 `RVCConverter.convert()`。檔案已刪除，
> 以下保留為演算法參考。

**功能**：將長音訊找到適合切割的靜音點，避免在有聲音處截斷。

```python
def find_cut_points(
    audio: np.ndarray,
    sr: int,
    min_silence_ms: int = 300,      # 靜音最短持續時間才算切割點
    silence_threshold_db: float = -40.0,  # 靜音門檻
    max_segment_sec: float = 15.0,  # 單段最長秒數（強制切割）
    overlap_ms: int = 150,          # 每段前後各延伸的 overlap 毫秒
) -> list[dict]:
    """
    回傳:
      [
        {"start": int, "end": int, "padded_start": int, "padded_end": int},
        ...
      ]
      start/end: 實際切割點（樣本數）
      padded_start/padded_end: 含 overlap 的範圍（供 RVC 輸入）
    """
```

**演算法**：
1. `librosa.effects.split()` 找非靜音區域
2. 靜音段超過 `min_silence_ms` → 標記為切割候選
3. 若兩個切割候選之間的音訊超過 `max_segment_sec` → 在中點強制切割
4. 各段加上 `overlap_ms` 的 padding（邊界做 clamp 處理）

---

### `voice/crossfade.py` 〔已移除 — 死碼〕

> 未被任何節點使用；等效 overlap 拼接已內建於 `RVCConverter.convert()`。檔案已刪除，
> 以下保留為演算法參考。


**功能**：將 RVC 轉換後的分段音訊無縫拼接。

```python
def concat_with_crossfade(
    segments: list[np.ndarray],     # 各段轉換後音訊（含 overlap）
    cut_points: list[dict],         # find_cut_points 的回傳值
    sr: int,
    fade_ms: int = 100,             # cross-fade 區域長度
) -> np.ndarray:
    """
    拼接策略：
      - overlap 區域：線性 cross-fade（前段 fade-out × 後段 fade-in）
      - 非 overlap 區域：直接拼接
      - 整體做 peak normalization 確保音量一致
    """
```

**cross-fade 公式**：
```
t ∈ [0, 1]（在 overlap 區間內線性遞增）
output[i] = segment_A[i] × (1 - t) + segment_B[i] × t
```

---

### `voice/resampler.py`

**功能**：高品質重採樣，處理輸入音訊與 RVC 模型原生採樣率之間的轉換。

```python
def resample(audio: np.ndarray, src_sr: int, dst_sr: int) -> np.ndarray:
    """使用 soxr 的 HQ 品質設定，無 aliasing。"""

def detect_sr(path: str) -> int:
    """讀取音訊檔案的採樣率（不載入全部音訊）。"""

def choose_model_sr(input_sr: int, available: list[int] = [32000, 40000, 48000]) -> int:
    """
    根據輸入採樣率選擇最接近的 RVC 模型版本。
    例：input_sr=44100 → 選 40000（避免向上過採樣）
    """
```

---

### `voice/auto_params.py`

**功能**：分析輸入音訊，自動建議 RVC 最佳參數。

```python
def analyze_audio(path: str) -> dict:
    """
    回傳:
    {
      "sr": int,                    # 偵測到的採樣率
      "duration": float,            # 秒數
      "snr_db": float,              # 估計訊噪比
      "is_speech": bool,            # 是否包含語音
      "f0_range": (float, float),   # 基頻範圍（Hz）
      "recommended_model_sr": int,  # 建議的 RVC 模型採樣率
      "recommended_index_rate": float,  # 建議 index_rate（0.0~1.0）
      "recommended_protect": float,     # 建議 protect（子音保護，0.0~0.5）
      "note": str,                  # 文字說明原因
    }
    """

def recommend_hop_length(duration_sec: float, sr: int) -> int:
    """
    根據音訊長度決定 F0 分析的 hop_length。
    短音訊（<5s）→ 小 hop（高解析）；長音訊 → 大 hop（降低計算量）。
    """
```

**參數決策邏輯**：

| 條件 | index_rate | protect |
|------|-----------|---------|
| SNR < 20dB（雜訊多）| 0.3 | 0.45 |
| SNR 20-40dB | 0.6 | 0.33 |
| SNR > 40dB（乾淨） | 0.75 | 0.25 |
| 日文語音（f0 高變化） | +0.0 | +0.05 |

---

### `voice/rvc_wrapper.py`

**功能**：統一封裝 RVC 推理，不依賴 RVC WebUI 啟動。

```python
class RVCConverter:
    def __init__(
        self,
        model_path: str,      # .pth 檔案路徑
        index_path: str = "", # .index 檔案路徑（空字串則不使用）
        device: str = "cuda", # "cuda" / "cpu"
    ): ...

    def convert(
        self,
        audio: np.ndarray,
        src_sr: int,
        f0_method: str = "harvest",   # "harvest" / "crepe" / "rmvpe"
        f0_up_key: int = 0,           # 音高偏移（半音）
        index_rate: float = 0.6,
        protect: float = 0.33,
        filter_radius: int = 3,
    ) -> tuple[np.ndarray, int]:
        """回傳 (converted_audio, output_sr)"""
```

**注意**：`RVCConverter` 假設使用者已安裝 RVC 依賴，`__init__` 中做 import 而非 top-level，失敗時印出清楚的安裝提示。

---

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

---

## ComfyUI 節點規格（`voice_nodes.py`）

所有節點 `CATEGORY = "MisakaNodes/Voice"`

> **實作狀態（2026-06）**：本規格為設計藍圖。實際節點實作位於 `nodes/voice/`，
> 已註冊的節點為 `MisakaVCLoadModel` / `MisakaVCAutoParams` / `MisakaVCConvertBatch` /
> `MisakaVCAudioInfo` / `MisakaVCPMGenerate`（TTS）。
> **Node 4/5 即時串流（`MisakaVCRealtimeStart` / `MisakaVCRealtimeStop`）尚未實作為 ComfyUI 節點**：
> 底層引擎 `voice/realtime_stream.py:RealtimeVCStream` 已存在，但沒有對應的節點類別、
> `VC_STREAM` 型別串接或 JS 裝置列舉支援，因此目前不在節點清單中。下方規格保留為待辦藍圖，
> 不代表已交付功能。

---

### Node 1：`MisakaVCLoadModel`

**用途**：載入 RVC 模型，建立 `RVCConverter` 實例。

```python
INPUT_TYPES:
  required:
    model_path:  STRING  （.pth 完整路徑）
    f0_method:   COMBO   ["harvest", "crepe", "rmvpe"]  default="harvest"
    device:      COMBO   ["cuda", "cpu"]                default="cuda"
  optional:
    index_path:  STRING  （.index 完整路徑，空白則不使用）

RETURN_TYPES:  ("VC_MODEL",)
RETURN_NAMES: ("vc_model",)
```

---

### Node 2：`MisakaVCAutoParams`

**用途**：分析音訊，自動建議轉換參數。

```python
INPUT_TYPES:
  required:
    audio_path:  STRING

RETURN_TYPES:  ("VC_PARAMS", "STRING")
RETURN_NAMES: ("vc_params", "analysis_report")
```

`VC_PARAMS` 為包含 `index_rate / protect / f0_up_key / filter_radius / model_sr` 的 dict。
`analysis_report` 為純文字說明（可接到 ShowText 節點）。

---

### Node 3：`MisakaVCConvertBatch`

**用途**：長音訊 batch 轉換（含自動分段 + cross-fade 拼接）。

```python
INPUT_TYPES:
  required:
    vc_model:    VC_MODEL
    audio_path:  STRING              （輸入音訊路徑）
    output_path: STRING              （輸出路徑，含副檔名）
  optional:
    vc_params:   VC_PARAMS           （接 AutoParams；不接則使用下方手動值）
    f0_up_key:       INT    default=0,    min=-12, max=12
    index_rate:      FLOAT  default=0.6, min=0.0,  max=1.0, step=0.01
    protect:         FLOAT  default=0.33,min=0.0,  max=0.5, step=0.01
    filter_radius:   INT    default=3,   min=0,    max=7
    min_silence_ms:  INT    default=300, min=100,  max=2000
    overlap_ms:      INT    default=150, min=50,   max=500
    fade_ms:         INT    default=100, min=10,   max=300
    max_segment_sec: FLOAT  default=15.0,min=3.0,  max=60.0

RETURN_TYPES:  ("STRING", "STRING")
RETURN_NAMES: ("output_path", "report")
```

**執行流程（實際實作）**：
1. 載入音訊 → `detect_sr()` → 轉單聲道 float32
2. `converter.convert()` —— 分段（靜音切點）與 overlap 拼接由 `RVCConverter.convert()`
   內部處理（Ultimate-RVC 演算法），不需外部 `find_cut_points` / `concat_with_crossfade`
3. 若提供 `output_path` 則 `soundfile.write()` 輸出，否則回傳 `AUDIO`

> 註：上方 `min_silence_ms` / `overlap_ms` / `fade_ms` / `max_segment_sec` 為原規格的
> 外部分段參數，實際實作未暴露 —— 分段已內建於 wrapper，這些旋鈕目前不存在。

---

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

---

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

---

### Node 6：`MisakaVCAudioInfo`

**用途**：顯示音訊基本資訊（不轉換），方便 debug。

```python
INPUT_TYPES:
  required:
    audio_path: STRING

RETURN_TYPES:  ("STRING",)
RETURN_NAMES: ("info",)
```

輸出格式：
```
路徑: xxx.wav
時長: 3m 24s
採樣率: 44100 Hz → 建議模型: 40000 Hz
聲道: 1 (mono)
SNR 估計: 38.2 dB
F0 範圍: 120~380 Hz
```

---

## 型別定義

ComfyUI 需在 `__init__.py` 新增自訂型別（讓節點之間可以連線）：

```python
# voice 型別（需在 NODE_CLASS_MAPPINGS 旁邊定義）
# ComfyUI 識別自訂型別的方式：RETURN_TYPES 中用大寫字串即可，
# 不需額外宣告，只要收發節點用相同字串就會自動連線。

# VC_MODEL  → RVCConverter 實例
# VC_PARAMS → dict（index_rate, protect, f0_up_key, filter_radius, model_sr）
# VC_STREAM → RealtimeVCStream 實例
```

---

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

---

## 實作注意事項

1. **RVC import 保護**：`rvc_wrapper.py` 的 `from rvc.xxx import ...` 全部包在 `try/except ImportError`，失敗時 `print("[MisakaVC] 請安裝 RVC 依賴：...")` 而不是 crash ComfyUI。

2. **GPU 記憶體**：`RVCConverter.__init__` 載入模型後呼叫 `torch.cuda.empty_cache()`；batch 轉換各段之間也清一次。

3. **執行緒安全**：`MisakaVCRealtimeStart` 的 stream handle 要用 `threading.Lock` 保護狀態，避免重複啟動。

4. **輸出採樣率**：batch 轉換的最終輸出維持 RVC 模型的原生採樣率（32k/40k/48k），不在 pipeline 中途降採樣。若需要特定格式，由使用者在節點後接 `MisakaResample` 節點。

5. **Windows 路徑**：所有 `os.path` 呼叫一律用 `Path()` 包裝，避免反斜線問題。

---

## 不在本規格範圍內

- RVC 模型訓練（需另外使用 RVC WebUI / trainer）
- F0 演算法實作（直接使用 RVC 內建的 harvest / crepe / rmvpe）
- 臉部 / 影像轉換（設計上預留接口，但不在此實作）
