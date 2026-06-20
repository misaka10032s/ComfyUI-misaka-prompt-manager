# ComfyUI-Misaka-Prompt-Manager

[English](#english) | [繁體中文](#繁體中文) | [日本語](#日本語) | [Security / 資安](#security)

---

<a name="english"></a>
## English

ComfyUI extension for managing prompt profiles, dynamic prompts, and model assets.

### Nodes Overview

#### 1. Misaka Profile Factory (Editor/Saver)
**Purpose:** Create, edit, and save reusable prompt profiles (Checkpoint + LoRAs + Prompts).
- **Features:** Supports dynamic LoRA inputs, categorized prompt fields, and filename templating (e.g., `%Seed.seed%`). Includes a `note` field for metadata like Civitai URLs.

#### 2. Misaka Prompt Manager (Loader)
**Purpose:** Load and apply saved profiles.
- **Features:** Automatically loads assets and can auto-populate workflow nodes (e.g., populating a "note" node) when triggered via the UI.

#### 3. Misaka Prompt Builder (Multi-Concat)
**Purpose:** Modular prompt building.
- **Features:** Automatically adds new text inputs as you type, allowing for unlimited modular prompt concatenation.

#### 4. Misaka Prompt Text
**Purpose:** A prompt input node with two fields — a single-line `alias` (used as folder name) and a multiline `text` field. Outputs a `MISAKA_PROMPT` bundle for use with Misaka Loop Prompt.

#### 5. Misaka Ckpt Name
**Purpose:** Checkpoint dropdown that outputs the filename as a STRING. Connect multiple instances to Misaka Loop Ckpt for cross-product generation.

#### 6. Misaka Loop Ckpt
**Purpose:** Replaces the standard checkpoint loader in cross-generation workflows. Accepts multiple checkpoint name inputs (dynamic slots), automatically cycles through them across runs.
- **Outputs:** `MODEL`, `CLIP`, `VAE`, `ckpt_name` (no extension), `run_info` (e.g. `run 2/6 | ckpt 1/2: modelA | prompt 2/3`)
- **reset_on_run:** Toggle to restart the cycle from the first combination on the next run.

#### 7. Misaka Loop Prompt
**Purpose:** Replaces the standard CLIP Text Encode node. Accepts multiple `MISAKA_PROMPT` inputs (dynamic slots), encodes the selected prompt for the current run.
- **Inputs:** `clip`, `ckpt_name` (optional, from Loop Ckpt), `base_folder` (default: `images/test`)
- **Outputs:** `CONDITIONING`, `formatted_name` (e.g. `images/test/alias/modelA`) — connect directly to SaveImage `filename_prefix`.

#### Usage: Cross-generation workflow
1. Add one **Misaka Ckpt Name** per checkpoint, connect all to **Misaka Loop Ckpt**.
2. Add one **Misaka Prompt Text** per prompt, connect all to **Misaka Loop Prompt**.
3. Connect `ckpt_name` from Loop Ckpt → Loop Prompt.
4. Connect `formatted_name` → SaveImage `filename_prefix`.
5. Set ComfyUI **Batch count** to (number of checkpoints × number of prompts), press Queue once.

#### 8. Misaka Scale Preset / Misaka Scale Custom
**Purpose:** Resolution helper nodes (category `MisakaNodes`) that output `width`, `height`, `scaled_width`, `scaled_height`, and an `info` string — feed the dimensions to an `EmptyLatentImage` and the scaled pair to an upscaler.
- **Misaka Scale Preset:** Pick a curated SD1.5 / SDXL resolution from a dropdown (e.g. `832×1216 (2:3 XL)`) and a `scale` (1.0–8.0). Outputs the base size and the ×scale size (rounded to multiples of 8).
- **Misaka Scale Custom:** Choose an `aspect_ratio` (or `free`) plus `width`/`height`; setting one dimension to `0` derives it from the ratio. `scale` produces the upscaled pair. Click **Calculate** in the UI to resolve both dimensions before running.

#### Voice nodes (category `MisakaNodes/Voice`)
> Optional. Require the voice dependencies in `requirements.txt` (RVC / VoxCPM packages are optional and may need build tools — see that file).

- **Misaka VC Load Model** — Loads an RVC `.pth` model (optional `.index`) into a `VC_MODEL`. `f0_method` (`harvest` / `crepe` / `rmvpe`) and `device` (`cuda` / `cpu`).
- **Misaka VC Auto Params** — Analyses an audio file and suggests conversion parameters (`VC_PARAMS`) plus a text report.
- **Misaka VC Convert Batch** — Converts a whole audio file with an RVC `VC_MODEL`. Long-audio silent-point chunking and overlap are handled internally by the converter. Knobs: `f0_up_key`, `index_rate`, `protect`, `rms_mix_rate`; optional `output_path` to write a WAV/FLAC/OGG/MP3. Outputs `AUDIO` + a report.
- **Misaka VC Audio Info** — Prints basic audio info (sample rate, duration) without converting; handy for debugging.
- **Misaka VCPM Generate (TTS)** — VoxCPM TTS with zero-shot voice cloning. Inputs: `model_version` (`VoxCPM2` ref-WAV-only, or `VoxCPM1.5` which also needs `prompt_text` = transcript of the reference), `text`, `reference_audio`. Tuning: `inference_timesteps`, `cfg_value`, `speed`, `split_threshold` (long text is auto-split into chunks), `seed`. Outputs `AUDIO` + an info string.

> **Note:** Realtime mic↔speaker voice conversion (`MisakaVCRealtimeStart/Stop`) is described in `SPEC-voice-conversion.md` but is **not implemented as a node** — only a low-level engine exists.

#### Utility: checkModelType.py
- **Function:** Scans profiles, identifies model types (Pony/Illustrious) via Civitai URLs in notes, automatically moves files to correct folders, updates checkpoints, and cleans up empty directories.

---

<a name="繁體中文"></a>
## 繁體中文

用於管理提示詞設定檔 (Profiles)、動態提示詞及模型資產的 ComfyUI 擴充功能。

### 節點功能介紹

#### 1. Misaka Profile Factory (編輯與儲存)
**用途：** 建立、編輯並儲存可重複使用的設定檔 (包含 Checkpoint、LoRAs 與提示詞)。
- **特色：** 支援動態 LoRA 欄位、分類提示詞輸入，以及檔案名稱模板 (例如 `%Seed.seed%`)。包含一個 `note` 欄位供記錄 Civitai 網址等資訊。

#### 2. Misaka Prompt Manager (載入器)
**用途：** 載入並套用儲存的設定檔。
- **特色：** 自動載入模型資產，並可透過 UI 觸發自動填入工作流中的特定節點 (例如將筆記內容填入名為 "note" 的節點)。

#### 3. Misaka Prompt Builder (多段串接)
**用途：** 模組化提示詞建構。
- **特色：** 隨著輸入內容自動增加新的文字區塊，支援無限段落的提示詞動態串接。

#### 4. Misaka Prompt Text
**用途：** 提示詞輸入節點，包含單行 `alias`（作為存檔資料夾名稱）與多行 `text` 欄位，輸出 `MISAKA_PROMPT` 供 Misaka Loop Prompt 使用。

#### 5. Misaka Ckpt Name
**用途：** Checkpoint 下拉選單，輸出檔名字串。連接多個至 Misaka Loop Ckpt 即可進行交叉生圖。

#### 6. Misaka Loop Ckpt
**用途：** 在交叉生圖 workflow 中取代標準 checkpoint 載入節點。接受多個 checkpoint 名稱輸入（動態插槽），每次執行自動切換。
- **輸出：** `MODEL`、`CLIP`、`VAE`、`ckpt_name`（無副檔名）、`run_info`（例如 `run 2/6 | ckpt 1/2: modelA | prompt 2/3`）
- **reset_on_run：** 勾選後下次執行從第一個組合重新開始。

#### 7. Misaka Loop Prompt
**用途：** 取代標準 CLIP Text Encode 節點。接受多個 `MISAKA_PROMPT` 輸入（動態插槽），每次執行自動編碼對應的提示詞。
- **輸入：** `clip`、`ckpt_name`（選填，來自 Loop Ckpt）、`base_folder`（預設：`images/test`）
- **輸出：** `CONDITIONING`、`formatted_name`（例如 `images/test/alias/modelA`）— 直接接到 SaveImage 的 `filename_prefix`。

#### 使用方式：交叉生圖 workflow
1. 每個 checkpoint 放一個 **Misaka Ckpt Name**，全部接到 **Misaka Loop Ckpt**。
2. 每組提示詞放一個 **Misaka Prompt Text**，全部接到 **Misaka Loop Prompt**。
3. 將 Loop Ckpt 的 `ckpt_name` 接到 Loop Prompt。
4. 將 `formatted_name` 接到 SaveImage 的 `filename_prefix`。
5. ComfyUI 的 **Batch count** 設為（checkpoint 數 × prompt 數），按一次 Queue。

#### 8. Misaka Scale Preset / Misaka Scale Custom
**用途：** 解析度輔助節點（分類 `MisakaNodes`），輸出 `width`、`height`、`scaled_width`、`scaled_height` 與一段 `info` 文字 —— 把尺寸接到 `EmptyLatentImage`，放大尺寸接到放大節點。
- **Misaka Scale Preset：** 從下拉選單挑選整理好的 SD1.5 / SDXL 解析度（例如 `832×1216 (2:3 XL)`）與 `scale`（1.0–8.0），輸出原始尺寸與 ×scale 尺寸（對齊 8 的倍數）。
- **Misaka Scale Custom：** 選擇 `aspect_ratio`（或 `free`）並填 `width`/`height`；其中一邊填 `0` 會依比例推算另一邊。`scale` 產生放大後尺寸。執行前可在 UI 按 **Calculate** 先解出兩邊尺寸。

#### 語音節點（分類 `MisakaNodes/Voice`）
> 選用功能。需安裝 `requirements.txt` 內的語音相依套件（RVC / VoxCPM 為選用，可能需要編譯工具，詳見該檔）。

- **Misaka VC Load Model** —— 載入 RVC `.pth` 模型（可選 `.index`）成 `VC_MODEL`。可設 `f0_method`（`harvest` / `crepe` / `rmvpe`）與 `device`（`cuda` / `cpu`）。
- **Misaka VC Auto Params** —— 分析音訊並建議轉換參數（`VC_PARAMS`）及文字報告。
- **Misaka VC Convert Batch** —— 以 RVC `VC_MODEL` 轉換整段音訊。長音訊的靜音切點分段與 overlap 由轉換器內部處理。可調 `f0_up_key`、`index_rate`、`protect`、`rms_mix_rate`；填 `output_path` 可輸出 WAV/FLAC/OGG/MP3。輸出 `AUDIO` 與報告。
- **Misaka VC Audio Info** —— 不轉換，僅顯示音訊基本資訊（採樣率、時長），方便除錯。
- **Misaka VCPM Generate (TTS)** —— VoxCPM 語音合成 + 零樣本語音克隆。輸入：`model_version`（`VoxCPM2` 僅需參考 WAV，或 `VoxCPM1.5` 另需 `prompt_text` = 參考音訊的逐字稿）、`text`、`reference_audio`。可調 `inference_timesteps`、`cfg_value`、`speed`、`split_threshold`（長文字自動分段）、`seed`。輸出 `AUDIO` 與資訊文字。

> **注意：** 即時麥克風↔喇叭語音轉換（`MisakaVCRealtimeStart/Stop`）在 `SPEC-voice-conversion.md` 有描述，但**尚未實作為節點** —— 目前僅有底層引擎。

#### 工具程式：checkModelType.py
- **功能：** 掃描設定檔，透過筆記中的 Civitai 連結判斷模型類型 (Pony/Illustrious)，自動將檔案移動至正確資料夾、更新 Checkpoint 欄位，並清理空資料夾。

---

<a name="日本語"></a>
## 日本語

プロンプトプロファイル、動的プロンプト、およびモデルアセットを管理するための ComfyUI 拡張機能です。

### ノードの概要

#### 1. Misaka Profile Factory (エディタ/保存)
**目的:** 再利用可能なプロファイル (チェックポイント + LoRA + プロンプト) を作成、編集、および保存します。
- **特徴:** 動的な LoRA 入力、カテゴリ分けされたプロンプトフィールド、ファイル名テンプレート (例: `%Seed.seed%`) をサポート。Civitai URL などのメタデータ用の `note` フィールドが含まれています。

#### 2. Misaka Prompt Manager (ローダー)
**目的:** 保存されたプロファイルをロードして適用します。
- **特徴:** アセットを自動的にロードし、UI を介してワークフロー内の特定のノード (例: "note" という名前のノード) に自動入力することができます。

#### 3. Misaka Prompt Builder (複数連結)
**目的:** モジュール式プロンプトの構築。
- **特徴:** 入力に応じて新しいテキスト入力フィールドを自動的に追加し、無制限のプロンプト連結が可能です。

#### 4. Misaka Prompt Text
**目的:** エイリアス（フォルダ名用の単行）とテキスト（複数行）の2フィールドを持つプロンプト入力ノード。`MISAKA_PROMPT` として Misaka Loop Prompt に渡します。

#### 5. Misaka Ckpt Name
**目的:** チェックポイントのドロップダウン。ファイル名を STRING として出力します。複数接続することで交差生成が可能です。

#### 6. Misaka Loop Ckpt
**目的:** 交差生成ワークフローで標準チェックポイントローダーを置き換えます。複数のチェックポイント名を受け取り（動的スロット）、実行ごとに自動で切り替えます。
- **出力:** `MODEL`、`CLIP`、`VAE`、`ckpt_name`（拡張子なし）、`run_info`（例: `run 2/6 | ckpt 1/2: modelA | prompt 2/3`）
- **reset_on_run:** オンにすると次回実行時に最初の組み合わせからリセットします。

#### 7. Misaka Loop Prompt
**目的:** 標準 CLIP Text Encode ノードを置き換えます。複数の `MISAKA_PROMPT` 入力を受け取り（動的スロット）、現在の実行に対応するプロンプトをエンコードします。
- **入力:** `clip`、`ckpt_name`（任意、Loop Ckpt から）、`base_folder`（デフォルト: `images/test`）
- **出力:** `CONDITIONING`、`formatted_name`（例: `images/test/alias/modelA`）— SaveImage の `filename_prefix` に直接接続。

#### 使用方法: 交差生成ワークフロー
1. チェックポイントごとに **Misaka Ckpt Name** を配置し、すべて **Misaka Loop Ckpt** に接続。
2. プロンプトごとに **Misaka Prompt Text** を配置し、すべて **Misaka Loop Prompt** に接続。
3. Loop Ckpt の `ckpt_name` を Loop Prompt に接続。
4. `formatted_name` を SaveImage の `filename_prefix` に接続。
5. ComfyUI の **Batch count** を（チェックポイント数 × プロンプト数）に設定し、Queue を1回押す。

#### 8. Misaka Scale Preset / Misaka Scale Custom
**目的:** 解像度補助ノード（カテゴリ `MisakaNodes`）。`width`、`height`、`scaled_width`、`scaled_height` と `info` 文字列を出力します。サイズを `EmptyLatentImage` に、拡大サイズをアップスケーラーに接続します。
- **Misaka Scale Preset:** 厳選した SD1.5 / SDXL 解像度（例: `832×1216 (2:3 XL)`）と `scale`（1.0–8.0）をドロップダウンで選択。元サイズと ×scale サイズ（8 の倍数に丸め）を出力します。
- **Misaka Scale Custom:** `aspect_ratio`（または `free`）と `width`/`height` を指定。一方を `0` にすると比率からもう一方を算出します。`scale` で拡大後サイズを生成。実行前に UI の **Calculate** で両寸法を確定できます。

#### 音声ノード（カテゴリ `MisakaNodes/Voice`）
> オプション。`requirements.txt` の音声依存パッケージが必要です（RVC / VoxCPM はオプションでビルドツールが要る場合あり。同ファイル参照）。

- **Misaka VC Load Model** — RVC `.pth` モデル（任意で `.index`）を `VC_MODEL` として読み込み。`f0_method`（`harvest` / `crepe` / `rmvpe`）と `device`（`cuda` / `cpu`）。
- **Misaka VC Auto Params** — 音声を分析し変換パラメータ（`VC_PARAMS`）とテキストレポートを提案。
- **Misaka VC Convert Batch** — RVC `VC_MODEL` で音声ファイル全体を変換。長尺音声の無音点分割とオーバーラップはコンバーター内部で処理されます。調整: `f0_up_key`、`index_rate`、`protect`、`rms_mix_rate`。`output_path` で WAV/FLAC/OGG/MP3 出力。`AUDIO` とレポートを出力。
- **Misaka VC Audio Info** — 変換せず音声の基本情報（サンプルレート、長さ）を表示。デバッグ用。
- **Misaka VCPM Generate (TTS)** — VoxCPM による TTS + ゼロショット音声クローン。入力: `model_version`（`VoxCPM2` は参照 WAV のみ、`VoxCPM1.5` は `prompt_text` = 参照音声の文字起こしも必要）、`text`、`reference_audio`。調整: `inference_timesteps`、`cfg_value`、`speed`、`split_threshold`（長文は自動分割）、`seed`。`AUDIO` と情報文字列を出力。

> **注意:** リアルタイムのマイク↔スピーカー音声変換（`MisakaVCRealtimeStart/Stop`）は `SPEC-voice-conversion.md` に記載されていますが、**ノードとしては未実装**です（低レベルエンジンのみ存在）。

#### ユーティリティ: checkModelType.py
- **機能:** プロファイルをスキャンし、ノート内の Civitai URL を介してモデルタイプ (Pony/Illustrious) を判別します。ファイルを正しいフォルダに自動的に移動し、チェックポイントを更新して、空のディレクトリを削除します。

---

<a name="security"></a>
## Security / 資安警示 / セキュリティ

**EN —**
- **Do not expose ComfyUI with `--listen` on an untrusted network.** This extension adds server routes (`/misaka/load_profile`, `/misaka/save_profile`, …) that read and write files under the profile storage directory. Profile names are now validated against path traversal, but the safest posture is to keep ComfyUI bound to `127.0.0.1`.
- **RVC models are loaded with `torch.load(weights_only=False)`** (`voice/rvc_wrapper.py:369`), which **deserializes arbitrary Python pickle** and can execute code on load. **Only load `.pth` RVC models from sources you trust.**

**繁體中文 —**
- **請勿以 `--listen` 將 ComfyUI 暴露到不信任的網路。** 本擴充功能新增了會在設定檔儲存目錄下讀寫檔案的伺服器路由（`/misaka/load_profile`、`/misaka/save_profile` 等）。設定檔名稱現已加上 path traversal 防護，但最安全的做法仍是讓 ComfyUI 綁定在 `127.0.0.1`。
- **RVC 模型以 `torch.load(weights_only=False)` 載入**（`voice/rvc_wrapper.py:369`），會**反序列化任意 Python pickle**，載入時可能執行程式碼。**僅載入可信任來源的 `.pth` RVC 模型。**

**日本語 —**
- **信頼できないネットワークで `--listen` を使って ComfyUI を公開しないでください。** 本拡張はプロファイル保存ディレクトリ配下でファイルを読み書きするサーバールート（`/misaka/load_profile`、`/misaka/save_profile` など）を追加します。プロファイル名はパストラバーサル対策済みですが、ComfyUI を `127.0.0.1` にバインドしておくのが最も安全です。
- **RVC モデルは `torch.load(weights_only=False)` で読み込まれます**（`voice/rvc_wrapper.py:369`）。これは**任意の Python pickle をデシリアライズ**し、読み込み時にコードを実行し得ます。**信頼できる提供元の `.pth` RVC モデルのみを読み込んでください。**