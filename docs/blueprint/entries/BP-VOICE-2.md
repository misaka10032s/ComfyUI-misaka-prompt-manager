---
id: BP-VOICE-2
title: VCPM TTS 零樣本語音克隆（VoxCPM）
system: voice
tags: [tts, voxcpm, voice-cloning]
status: 已完成
request_verbatim: >-
  「voice tts new node」（git commit 33ff949 訊息；無先於此的獨立逐字需求文件，以 commit
  message 作為現存最早可證明來源。README 現有描述見 exec_links）
decided_date: 2026-04-20
exec_links:
  - nodes/voice/pm_generate.py
  - nodes/voice/_shared.py（_vcpm_load / _vcpm_synth_one / _split_for_tts / _prepare_reference_wav）
  - js/voice.js（前端檔案挑選器，見 BP-UI-4）
  - README.md#voice-nodes（Misaka VCPM Generate (TTS)）
done_date: 2026-05-24
revisions:
  - date: 2026-04-20
    summary: "commit 33ff949 — 初版 MisakaVCPMGenerate（voice_nodes.py）"
  - date: 2026-05-24
    summary: "commit b13acaa — 拆分到 nodes/voice/pm_generate.py，共用邏輯併入 nodes/voice/_shared.py"
origin: "git commit 33ff949 訊息"
---

## 設計說明

VoxCPM TTS + 零樣本語音克隆（zero-shot voice cloning）——只需一段參考音訊即可合成任意文字的
語音，音色模仿參考音訊。

`INPUT_TYPES`：`model_version`（`VoxCPM2` 僅需 `reference_audio`；`VoxCPM1.5` 額外需要
`prompt_text` = 參考音訊的逐字稿）、`text`、`reference_audio`；可調
`inference_timesteps`/`cfg_value`/`speed`/`split_threshold`/`seed`。輸出 `AUDIO` + 資訊文字。

### 執行流程（`nodes/voice/pm_generate.py:generate` + `_shared.py`）

1. `_normalize_text()`：把多個換行摺成句號，單換行去除。
2. `_prepare_reference_wav()`：參考音訊 resample + mono 到 24kHz（VoxCPM 要求）。
3. `_vcpm_load()`：依 `model_version` 對應 HuggingFace repo（`openbmb/VoxCPM2` /
   `openbmb/VoxCPM1.5`），模型物件快取於模組級 `_VCPM_CACHE`（同一 ComfyUI 進程內只載入一次）。
4. 長文字自動分段（`_split_for_tts`，依中日文句尾標點 `。！？…` 切句,合併到最小塊長度
   `min_chunk`），逐段呼叫 `_vcpm_synth_one()` 合成,段落間依需要插入 `PAUSE`（0.25s）靜音。
5. 各段音訊寫暫存檔再讀回拼接（`tempfile`,避免長文字合成時記憶體累積）,`speed != 1.0` 時用
   `librosa.effects.time_stretch()` 調整整體語速；輸出前做 peak normalize 避免破音。
6. `seed`（-1 = 隨機）同時設定 `torch`/`numpy` 隨機種子，確保可重現。

### Windows 依賴注意事項

`_vcpm_load()` 讀取 `FFMPEG_DLL_DIR` 環境變數並 `os.add_dll_directory()`——VoxCPM 在 Windows
上需要 FFmpeg 共用 DLL（無法純用 pip 安裝),見 `requirements.txt` 安裝說明。
