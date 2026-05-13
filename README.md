# ComfyUI-Misaka-Prompt-Manager

[English](#english) | [繁體中文](#繁體中文) | [日本語](#日本語)

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

#### ユーティリティ: checkModelType.py
- **機能:** プロファイルをスキャンし、ノート内の Civitai URL を介してモデルタイプ (Pony/Illustrious) を判別します。ファイルを正しいフォルダに自動的に移動し、チェックポイントを更新して、空のディレクトリを削除します。