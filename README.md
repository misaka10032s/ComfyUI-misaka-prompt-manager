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

#### ユーティリティ: checkModelType.py
- **機能:** プロファイルをスキャンし、ノート内の Civitai URL を介してモデルタイプ (Pony/Illustrious) を判別します。ファイルを正しいフォルダに自動的に移動し、チェックポイントを更新して、空のディレクトリを削除します。