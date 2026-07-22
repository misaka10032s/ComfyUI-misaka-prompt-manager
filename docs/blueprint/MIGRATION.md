# Blueprint 遷移對照表（ComfyUI-misaka-prompt-manager · P2）

> 依 `@PM/docs/superpowers/specs/2026-07-21-blueprint-system-design.md` §7 清舊協議。
>
> **狀態更新（2026-07-22）**：fresh subagent 驗證 PASS
> （`D:/backup/CSIA/@PM/state/runs/comfy-promptmgr-blueprint-seed/review.md`）。第 3 步驗證
> 已通過，第 4 步「移除」已執行：`docs/superpowers/specs/SPEC-voice-conversion.md` 已
> `git rm`（同 commit 隨附本檔更新）。git 歷史即封存，可用 `git show <前一個 commit>:
> docs/superpowers/specs/SPEC-voice-conversion.md` 找回全文。其餘判定
> （README.md/prompt/misaka_node.py.bak/.claude/CLAUDE.md KEEP）未變動，維持第 2–5 節判定。

---

## 1. `docs/superpowers/specs/SPEC-voice-conversion.md`（已移除，2026-07-22）→ 目標 BP 條目

| 章節 | 目標 BP 條目 | 落地內容 / 備註 |
|---|---|---|
| 目錄結構（新增部分）— `voice/` 底層引擎清單 | `BP-VOICE-1`（resampler/auto_params/rvc_wrapper）+ `BP-VOICE-3`（realtime_stream.py） | 「與原規格差異（誠實註記）」段落（segmentation.py/crossfade.py 已移除為死碼、節點實作位於 `nodes/voice/`）落地於 `BP-VOICE-1` revisions（對應 commit `a4eaba3`）|
| 目錄結構 — `nodes/voice/` 實際節點清單 | `BP-VOICE-1`（load_model/auto_params/convert_batch/audio_info）+ `BP-VOICE-2`（pm_generate） | 逐檔對應，非籠統一句話 |
| 依賴套件（requirements 新增）— 音訊處理段（librosa/soundfile/soxr/numpy） | `BP-VOICE-1` | RVC 批次轉換與 TTS 共用的音訊處理依賴 |
| 依賴套件 — 即時音訊串流段（sounddevice） | `BP-VOICE-3` | 僅 realtime 引擎使用，其餘節點不需要 |
| 依賴套件 — RVC 依賴段（faiss-gpu/torchcrepe/pyworld，需使用者自行安裝） | `BP-VOICE-1` | 對應 README `requirements.txt` 安裝說明章節（README 本身 KEEP，見下表） |
| 依賴套件 — 品質評估段（pesq，用於 auto_params） | `BP-VOICE-1` | `voice/auto_params.py:analyze_audio` 的 SNR/F0 估計目前未見 `pesq` 實際 import（規格提及但未在現有程式碼路徑找到使用點）——本表誠實記錄此落差，不臆測 |
| `voice/segmentation.py`〔已移除 — 死碼〕完整演算法規格 | `BP-VOICE-1`（revisions，commit `a4eaba3`） | 演算法本身已不存在於程式碼，規格文件保留原文作為歷史演算法參考（誠實註記已在 SPEC 原文中），不重複收錄進 BP body |
| `voice/crossfade.py`〔已移除 — 死碼〕完整演算法規格 | `BP-VOICE-1`（revisions，commit `a4eaba3`） | 同上 |
| `voice/resampler.py` 模組規格 | `BP-VOICE-1` | body「`RVCConverter`」段引用 `detect_sr`/`choose_model_sr` |
| `voice/auto_params.py` 模組規格 + 參數決策表 | `BP-VOICE-1` | body「自動參數建議」段完整落地決策表 |
| `voice/rvc_wrapper.py` `RVCConverter` 規格 | `BP-VOICE-1` | body「`RVCConverter`」段（含 2026-04-26 Ultimate-RVC 架構重寫的落地說明） |
| `voice/realtime_stream.py` `RealtimeVCStream` 規格 + 緩衝區設計 | `BP-VOICE-3` | body 完整落地，含「待判斷」現況誠實記錄 |
| ComfyUI 節點規格總覽段「實作狀態（2026-06）」誠實註記 | `BP-VOICE-1`（已交付節點）+ `BP-VOICE-3`（Node 4/5 未實作） | 此段本身就是 SPEC 作者對現況的誠實揭露，本次盤點逐字引用進 `BP-VOICE-3` frontmatter |
| Node 1 `MisakaVCLoadModel` | `BP-VOICE-1` | |
| Node 2 `MisakaVCAutoParams` | `BP-VOICE-1` | |
| Node 3 `MisakaVCConvertBatch` | `BP-VOICE-1` | 含「執行流程（實際實作）」與「原規格外部分段參數未暴露」的誠實註記 |
| Node 4 `MisakaVCRealtimeStart`〔未實作〕 | `BP-VOICE-3` | |
| Node 5 `MisakaVCRealtimeStop`〔未實作〕 | `BP-VOICE-3` | |
| Node 6 `MisakaVCAudioInfo` | `BP-VOICE-1` | |
| 型別定義（`VC_MODEL`/`VC_PARAMS`/`VC_STREAM`） | `VC_MODEL`/`VC_PARAMS` → `BP-VOICE-1`；`VC_STREAM` → `BP-VOICE-3` | ComfyUI 自訂型別無獨立條目，隨其消費節點記錄 |
| 即時 VC 與未來擴充（臉部轉換）的隔離設計 | `BP-VOICE-3` | multiprocessing 隔離設計完整落地於 body |
| 實作注意事項 1（RVC import 保護） | `BP-VOICE-1` | body 引用 `_RVCForkFinder` meta-path finder 的實際落地（比規格描述的簡單 try/except 更完整） |
| 實作注意事項 2（GPU 記憶體） | `BP-VOICE-1` | `nodes/voice/pm_generate.py` 的 `torch.cuda.empty_cache()` 呼叫點對應（TTS 側）；RVC 側對應 `voice/rvc_wrapper.py` |
| 實作注意事項 3（執行緒安全，`threading.Lock`） | `BP-VOICE-3` | 底層引擎 `RealtimeVCStream.__init__` 已有 `self._lock = threading.Lock()`——即使節點未交付，引擎本身已依此注意事項實作 |
| 實作注意事項 4（輸出採樣率不中途降採樣） | `BP-VOICE-1` | `MisakaVCConvertBatch` 輸出維持 RVC 模型原生採樣率，對應落地 |
| 實作注意事項 5（Windows 路徑用 `Path()`） | 不落地 BP 條目 — explicitly excluded | 純程式碼風格慣例，非產品設計決策，不適用於功能級 SSOT |
| 不在本規格範圍內 — RVC 模型訓練 | 不落地 BP 條目 — explicitly excluded | 明文非目標，且至今未有任何程式碼朝此方向開發，無需追蹤 |
| 不在本規格範圍內 — F0 演算法實作 | 不落地 BP 條目 — explicitly excluded | 同上，直接使用 RVC 內建演算法，非本專案自製 |
| 不在本規格範圍內 — 臉部/影像轉換 | 不落地 BP 條目 — explicitly excluded | SPEC 明文「設計上預留接口，但不在此實作」，屬於 BP-VOICE-3 body「隔離設計」段落已記錄的未來擴充占位，不需要獨立條目追蹤一個從未開工的功能 |

**判定：`SPEC-voice-conversion.md` 全檔內容已 100% 有著落**（每一節皆遷移到 BP 條目之一，
或明確排除並附理由；「依賴套件 — pesq」一項誠實記錄為規格與現有程式碼的落差，非遺漏)。

**已移除（2026-07-22，fresh subagent 驗證 PASS 後執行）**：`git rm
docs/superpowers/specs/SPEC-voice-conversion.md`（migrated, removed — 見上方狀態更新）。

---

## 2. `README.md` — 保留（使用者文件，非設計規格）

**判定：KEEP，不遷移，不編輯。** `README.md` 是三語（EN/zh-TW/日本語）**使用者文件**
（Task B 指示明文：「README.md = 使用者文件，KEEP（但註記其漂移項為 BP 條目/issue，不編輯
它）」），性質與 `docs/blueprint/` 的功能級設計 SSOT 不同——README 服務「怎麼用」，blueprint
服務「做了什麼、做到什麼程度」。以下記錄本次盤點發現的 README ↔ 實際程式碼落差，作為對應
BP 條目 body 內「誠實揭露」段落的來源，**不修改 README 本身**：

| README 落差 | 對應 BP 條目 | 落差內容 |
|---|---|---|
| 第 6/7 節「Misaka Loop Ckpt」/「Misaka Loop Prompt」描述的兩節點簡化介面 | `BP-IMG-3` | 現況已是五節點（`MisakaLoopCkpt`/`MisakaLoopPrompt`/`MisakaLoopCkptCore`/`MisakaLoopPromptCore`/`MisakaLoopManager`）架構，`b13acaa`（2026-05-24）拆分後 README 未同步更新，`BP-IMG-3` body「README 現況落差」段完整記錄 |
| 「Realtime VC」注意事項段已誠實記載未實作 | `BP-VOICE-3` | README 本身已誠實揭露（「僅有底層引擎」），與 blueprint 記錄一致,不算落差,僅互相引用 |
| 未提及 `MisakaImageProfileFactory.execute()` 的 `save_as_profile` 路徑防護缺口 | `BP-IMG-1` | README `## Security` 段只提到「設定檔名稱現已加上 path traversal 防護」，未區分「REST 路由/Manager 已修復」vs「Factory 節點內建存檔未修復」的差異——`BP-IMG-1`「已知問題」段補上此區分,不修改 README 用語（README 的概括陳述本身不算錯誤，只是不夠精確,留待使用者決定是否要更新 README 用語） |

---

## 3. `prompt`（repo root，原始需求逐字稿）— 保留

**判定：KEEP。** 這是使用者最原始的需求對話記錄（無檔案副檔名，UTF-8 文字檔），是
`BP-IMG-1`/`BP-IMG-2`/`BP-UI-1` 等條目 `request_verbatim`/`origin` 欄位的直接來源。
依 doc taxonomy,這類「需求原始記錄」不屬於「被 blueprint 取代的設計文件」——blueprint 的
`request_verbatim` 欄位本身就是从这个档案摘录逐字稿,原始檔案作為可回溯的第一手來源應保留,
不建議刪除。

檔案內容盤點涵蓋範圍：Profile Factory/Manager 初版需求（第 1–20 行）、Prompt Builder 需求
（第 22 行）、note 欄位需求（第 42–44 行）、以及檔案後段（第 26–50 行）提及但**與本 repo
無關**的外部工具（`checkModelType.py` 遷移到 `ComfyUI/user/default/misaka-prompt-sets`、
`downloadFromCivitai.py`）——這兩個工具已依當時需求移出本 repo（本次盤點確認 repo 內已無
`checkModelType.py`/`downloadFromCivitai.py` 檔案,`find` 掃描零命中),不追蹤為本 repo 的
blueprint 條目,理由：其執行位置已不在此 repo 的維護範圍內。

---

## 4. `misaka_node.py.bak` — 保留原位（歷史備份，非設計文件，本次不動）

**判定：KEEP,不刪除,不遷移。** commit `56444c8`（2026-04-17）把當時的單一 `misaka_node.py`
重命名為 `.bak` 後另起 `image_nodes.py`（後於 `b13acaa` 再拆成 `nodes/image/`
套件）。此檔案是**程式碼歷史快照**,不是設計規格文件,不在 §7 清舊協議「被 blueprint 取代
的設計文件」範圍內——協議管的是文字設計文件（SPEC/ADR/roadmap 等），不管原始碼快照的取捨。
是否刪除此備份檔屬於一般程式碼衛生決策（非 blueprint 遷移範疇),留給使用者/後續維護決定,
本次任務不代為刪除。

---

## 5. `.claude/CLAUDE.md` — 保留（制度文件，非設計規格）

**判定：KEEP。** 依 doc taxonomy,`CLAUDE.md` 是 AI 協作制度文件,不是產品設計規格。其中
「Realtime streaming nodes...NOT registered...do not delete without checking the roadmap
task first」與「Open security task: get_project path-traversal on project_id」兩條待辦,
已分別對應到 `BP-VOICE-3`（待判斷)與本次新發現的 `BP-IMG-1` 已知問題段（注意：CLAUDE.md
原文提到的是舊版 `get_project`,現有程式碼已無此函式名——`resolve_profile_path` 是後繼實作,
本次盤點確認實際殘留缺口在 `MisakaImageProfileFactory.execute()`,非 `get_project`,見
`BP-IMG-1`)。

---

## 6. 彙總

- **已移除（migrated → 已移除，2026-07-22，fresh subagent 驗證 PASS 後執行）**：
  1. `docs/superpowers/specs/SPEC-voice-conversion.md`
- **KEEP（不遷移，理由已列於上表）**：`README.md`、`prompt`、`misaka_node.py.bak`、
  `.claude/CLAUDE.md` = **4 份文件/檔案**。
- **本次盤點新發現、記錄進 blueprint 但不影響上述判定的落差**：
  1. `MisakaImageProfileFactory.execute()` 的 `save_as_profile` 路徑防護缺口（`BP-IMG-1`）。
  2. README Loop 節點介面描述落後於 `b13acaa` 拆分後的實際架構（`BP-IMG-3`）。
  3. SPEC 規格提及 `pesq`（品質評估）但現有 `voice/auto_params.py` 未見實際使用點（`BP-VOICE-1`）。

**完成**：清舊協議四步（盤點 → 遷移 → fresh subagent 驗證 → 移除）已全部走完，本檔案為
最終存檔紀錄；`docs/superpowers/specs/` 底下已無 `SPEC-voice-conversion.md`。
