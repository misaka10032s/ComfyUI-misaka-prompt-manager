---
id: BP-VOICE-1
title: RVC 批次語音轉換（Load Model / Auto Params / Convert Batch / Audio Info）
system: voice
tags: [rvc, voice-conversion, f0, batch]
status: 已完成
request_verbatim: >-
  「修正結構 — 分開 image新增 audio + video 類別的node」（git commit 56444c8 訊息，此 commit
  一次性新增完整 RVC 語音轉換節點群；SPEC-voice-conversion.md 隨同一 commit 建立，作為設計藍圖）
decided_date: 2026-04-17
exec_links:
  - docs/superpowers/specs/SPEC-voice-conversion.md
  - nodes/voice/load_model.py
  - nodes/voice/auto_params.py
  - nodes/voice/convert_batch.py
  - nodes/voice/audio_info.py
  - nodes/voice/_shared.py
  - voice/rvc_wrapper.py
  - voice/_safe_load.py（新增，2026-09-07，待回答 #49：weights_only=True 安全載入＋退回警告）
  - voice/auto_params.py
  - voice/resampler.py
  - js/voice.js（前端檔案挑選器，見 BP-UI-4）
  - README.md#voice-nodes
  - README.md#security（`torch.load(weights_only=False)` 風險警示；2026-09-07 起改為安全載入為主，見下方 qa_log）
superpowers:
  - path: docs/superpowers/specs/SPEC-voice-conversion.md
    label: 語音轉換 spec
done_date: 2026-06-20
revisions:
  - date: 2026-04-17
    summary: "commit 56444c8 — 初版 MisakaVCLoadModel/AutoParams/ConvertBatch/AudioInfo（voice_nodes.py + voice/rvc_wrapper.py 等底層引擎）；同時新增 MisakaVCRealtimeStart/Stop（見 BP-VOICE-3，從未註冊）"
  - date: 2026-04-21
    summary: "commit 3b256d9 — 改用暫存檔避免長音訊轉換時 GPU OOM"
  - date: 2026-04-26
    summary: "commit 2edfa05 — 重寫 RVCConverter 為 Ultimate-RVC 架構（voice/rvc_wrapper.py 內建靜音切點分段 + overlap 拼接，取代原規劃中獨立的 segmentation.py/crossfade.py）"
  - date: 2026-05-24
    summary: "commit b13acaa — 節點實作拆分到 nodes/voice/ 套件（load_model.py/auto_params.py/convert_batch.py/audio_info.py），底層引擎留在頂層 voice/"
  - date: 2026-06-20
    summary: "commit a4eaba3 — 移除從未被使用的死碼 voice/segmentation.py、voice/crossfade.py（等效邏輯已內建於 RVCConverter.convert()），修正 requirements.txt 過時註解"
  - date: 2026-09-07
    summary: "待回答 #49 security fix — 新增 voice/_safe_load.py：RVC .pth 模型改為先 torch.load(weights_only=True) 安全載入，失敗才退回 weights_only=False 並印出＋記錄明確警告；新增 MISAKA_PM_RVC_STRICT_LOAD=1 可停用退回；voice/rvc_wrapper.py 的 _RVCForkFinder 縮小作用範圍為僅在單次載入期間安裝／卸載；README.md #security 三語警示同步更新"
  - date: 2026-09-07
    summary: "FRESH opus 複核（F1–F7，見下方 qa_log）後的修復 pass — voice/_safe_load.py 決策邏輯改為先以 torch.serialization.get_unsafe_globals_in_checkpoint() 靜態掃描（不 unpickle）決定退回與否，不再靠攔截例外型別判斷（修正 F1：損毀／截斷／垃圾位元組檔案原本會誤觸退回並印出 RCE 警告，現在直接原樣往外拋、絕不退回、絕不印警告）；voice/rvc_wrapper.py 新增 _StaticForkGlobalPlaceholder，把 yuuka_best.pth 需要的唯一 fork 全域物件 ultimate_rvc.typing_extra.TrainingSampleRate 明確 allowlist 到安全路徑（修正 F2：站主兩個真實模型現在都走安全路徑、不再需要退回、不再印警告）；voice/_safe_load.py 與 tests/test_rvc_safe_load_torch.py 內「py -3.11 沒裝 torch」的斷言改為條件敘述（修正 F4）；voice/rvc_wrapper.py 模組 docstring 補上 _install_rvc_finder/_uninstall_rvc_finder 與 safe_globals 視窗的單執行緒假設說明（修正 F5，僅文件、無程式碼變更）；MISAKA_PM_RVC_STRICT_LOAD 改為接受 1/true/yes/on（大小寫不拘）（修正 F7）；docs/blueprint/entries/BP-VOICE-1.md 舊有 tests 記錄的『既有 62 個』算術錯誤修正為『既有 55 個』（修正 F3）"
origin: "docs/superpowers/specs/SPEC-voice-conversion.md（設計藍圖，2026-04-17 隨程式碼同時建立）"
tests:
  - date: 2026-09-07
    target: "voice/_safe_load.py:load_checkpoint()（safe-then-fallback 決策邏輯），voice/rvc_wrapper.py:load_rvc_checkpoint()/_rvc_safe_globals()/_install_rvc_finder()/_uninstall_rvc_finder()"
    action: >-
      quality-gates/run.py l0（G1 ruff／G2 mypy／G3 pytest／G3b assertion-presence，py -3.11，
      cwd=repo root）；另以 ComfyUI EMBEDDED 直譯器（D:/AIprojects/ComfyUI_windows_portable/
      python_embeded/python.exe，torch 2.11.0+cu128）單獨執行 tests/test_rvc_safe_load_torch.py
      （真 torch 版覆蓋，gate 直譯器上以 pytest.importorskip("torch") 判斷是否需跳過——本機
      py -3.11 實際上也裝有 torch 2.11.0+cu128，故 gate 執行時此檔並未被跳過，兩個直譯器下皆
      為真實執行，未依賴模擬）；另以唯讀 scratch script 驗證站主現有兩個真實 RVC 模型
      （makima-en-dub.pth／yuuka_best.pth）與 index 檔（yuuka.index／
      added_IVF73_Flat_nprobe_1_makima-en-dub_v2.index）
    expected: >-
      tests/test_rvc_safe_load.py（torch-free，7 tests）：安全路徑優先以 weights_only=True 呼叫；
      安全成功時不退回、不警告；pickle.UnpicklingError／RuntimeError 觸發退回並記錄＋印出警告
      （含檔名）；MISAKA_PM_RVC_STRICT_LOAD=1 時安全路徑失敗直接拋出 RuntimeError、絕不呼叫
      weights_only=False；非 pickle 例外（如 FileNotFoundError）原樣往外拋、不觸發退回。
      tests/test_rvc_safe_load_torch.py（真 torch，3 tests）：標準 RVC dict 形狀 checkpoint
      （tensor/list/str/int 組成）僅需安全路徑即可載入、無需任何客製 allowlist、無警告；含
      未被 allowlist 的自訂類別的 checkpoint 觸發安全路徑失敗、退回成功並記錄警告；strict 模式
      下同一 checkpoint 改為直接拋出。真實模型驗證：makima-en-dub.pth 與 yuuka_best.pth 用新
      loader 讀出的結果，逐 key／逐 tensor shape／逐 tensor 值比對均須與舊版
      weights_only=False 無條件載入結果完全相同；兩個 .index 檔（faiss，不受本次變更影響）
      須可正常載入。
    result: >-
      PASS — quality-gates/run.py l0 全綠：[G1] PASS — 24 total violation(s), 0 new vs baseline
      (24 pre-existing). ｜ [G2] PASS — 23 total error(s), 0 new vs baseline (23 pre-existing). ｜
      pytest：65 passed（既有 55 個 + 新增 tests/test_rvc_safe_load.py 7 個＋
      tests/test_rvc_safe_load_torch.py 3 個）｜ [G3b] PASS — 2 changed test file(s), all touched
      test functions assert something。quality-gates/ruff-baseline.json、mypy-baseline.json 均未
      變動。真實模型驗證（embedded 直譯器）：makima-en-dub.pth 安全路徑（weights_only=True）
      直接成功，無需退回；yuuka_best.pth 因含 GLOBAL ultimate_rvc.typing_extra.
      TrainingSampleRate（RVC fork 動態 placeholder 類別，依設計刻意不 allowlist）觸發安全路徑
      失敗，如預期退回並印出＋記錄警告後成功載入；兩者的新／舊 loader 結果經逐 key／逐 tensor
      比對均完全相同（457 個 weight key、config/version/sr/f0/info 等全部一致）。
      yuuka.index（ntotal=39984, d=768）、added_IVF73_Flat_nprobe_1_makima-en-dub_v2.index
      （ntotal=2862, d=768）皆正常載入，不受本次變更影響。（原始 result 記錄的『既有 62 個』
      為算術錯誤，2026-09-07 opus 複核 F3 指出後修正為『既有 55 個』——55 為
      test_path_traversal.py 7 個＋test_origin_guard.py 48 個，55+7+3=65。）
    evidence: tests/test_rvc_safe_load.py, tests/test_rvc_safe_load_torch.py
    executor: implementer-subagent（待回答 #49 security fix，2026-09-07）
  - date: 2026-09-07
    target: "voice/_safe_load.py:load_checkpoint()（F1 靜態掃描決策改寫），
      voice/rvc_wrapper.py:_rvc_safe_globals()/_StaticForkGlobalPlaceholder（F2 yuuka 安全路徑
      binding），voice/_safe_load.py:strict_mode_enabled()（F7 大小寫不拘）"
    action: >-
      FRESH opus 複核（F1–F7，見下方 qa_log）後的修復 pass。quality-gates/run.py l0（py -3.11，
      cwd=repo root）；另以 ComfyUI EMBEDDED 直譯器單獨執行
      tests/test_rvc_safe_load_torch.py；另以唯讀 scratch script 重新驗證站主現有兩個真實 RVC
      模型（makima-en-dub.pth／yuuka_best.pth）與其中一個 index 檔
      （added_IVF73_Flat_nprobe_1_makima-en-dub_v2.index）在 F1/F2 修復後的行為，並驗證損毀
      （截斷 zip）／垃圾位元組／空檔／不存在檔案這四種情況不再誤觸退回或印出警告。
    expected: >-
      F1：截斷 zip／垃圾位元組／空檔／缺檔 → 直接往外拋例外、torch.load 呼叫序列為空、不印警告；
      乾淨 checkpoint → 僅呼叫一次 weights_only=True、不印警告；含未被允許全域物件的 checkpoint
      → 僅呼叫一次 weights_only=False、印出＋記錄含檔名與全域物件名稱的警告；strict 模式下改為
      直接拋出、列出未被允許的全域物件名稱、torch.load 完全不被呼叫。F2：makima-en-dub.pth 與
      yuuka_best.pth 兩者在新 allowlist 下靜態掃描結果均為空（無未被允許全域物件），兩者皆走
      安全路徑、不印警告，且與舊版 weights_only=False 無條件載入結果逐 key／逐 tensor 完全相同。
      F7：MISAKA_PM_RVC_STRICT_LOAD 設為 1/true/TRUE/Yes/on 均視為啟用，0/false/空字串/2/no
      均視為停用。既有 82 項 pytest（55 既有＋test_rvc_safe_load.py 22 個＋
      test_rvc_safe_load_torch.py 5 個）全數維持通過，quality-gates 兩份 baseline 不變動。
    result: >-
      PASS — quality-gates/run.py l0 全綠（見下方 verbatim）。真實模型重新驗證（embedded
      直譯器，讀取後未修改／搬移／刪除任何站主檔案）：makima-en-dub.pth 與 yuuka_best.pth 兩者
      「unsafe globals (with F2 allowlist)」均為 []，兩者 NEW loader warned=False，兩者
      DEEP EQUAL(old, new)=True；added_IVF73_Flat_nprobe_1_makima-en-dub_v2.index 正常載入
      （ntotal=2862, d=768）。F1 損毀/垃圾/空檔/缺檔重新驗證（scratch script，torch.load 呼叫
      序列以 monkeypatch 記錄）：truncated zip → RAISED RuntimeError、calls=[]、
      warning printed=False；garbage bytes → RAISED ValueError、calls=[]、warning
      printed=False；empty file → RAISED ValueError、calls=[]、warning printed=False；missing
      file → RAISED FileNotFoundError、calls=[]、warning printed=False；clean real file →
      OK、calls=[True]、warning printed=False。
      Gate verbatim：
      [G1] PASS — 24 total violation(s), 0 new vs baseline (24 pre-existing).
      [G2] PASS — 23 total error(s), 0 new vs baseline (23 pre-existing).
      82 passed in 2.30s
      [G3b] PASS — 2 changed test file(s), all touched test functions assert something
      (base eb828b2880702c626ba59d27cfea468793704a83).
      Embedded 直譯器 tests/test_rvc_safe_load_torch.py：5 passed in 1.43s。
      blueprint-build.py --lint：lint OK, EXIT=0。
    evidence: tests/test_rvc_safe_load.py, tests/test_rvc_safe_load_torch.py, voice/_safe_load.py,
      voice/rvc_wrapper.py
    executor: implementer-subagent（待回答 #49 opus 複核 F1–F7 修復 pass，2026-09-07）
qa_log:
  - date: 2026-09-07
    summary: >-
      待回答 #49：voice/rvc_wrapper.py:369 原本無條件以 torch.load(weights_only=False) 載入
      工作流程挑選的 .pth 模型，等於載入不受信任的 RVC 模型檔即可執行任意程式碼；
      _RVCForkFinder（rvc_wrapper.py:64-110）進一步放寬 pickle 可還原的物件範圍（為了讓
      沒裝原始 RVC fork 套件的環境仍能還原完整模型物件而設的動態 placeholder 類別）。
      Owner 裁示（逐字）：「修：先安全載入（weights_only=True），失敗才退回舊方式並明確
      警告」，並要求「用站主現有 RVC 模型驗證仍可載」。變更：新增 voice/_safe_load.py，
      刻意不在模組頂層 import torch（延遲到函式內部），使其可在完全沒裝 torch 的直譯器
      下被單獨匯入與單元測試（本 repo 的 quality-gate 直譯器 py -3.11 名義上就是這種
      環境——但實測發現此機器的 py -3.11 其實也裝有 torch 2.11.0+cu128，與 embedded
      直譯器版本相同，因此本次驗證在兩邊都是真實執行，並非僅靠模擬）。load_checkpoint()
      決策邏輯：先在 voice/rvc_wrapper.py:_rvc_safe_globals() 提供的 allowlist（僅
      voice/rvc_model.py 內我們自己寫的 16 個 nn.Module 子類別——用於「整包 model 物件」
      pickle 變體，一般 dict 形狀 checkpoint 完全不需要任何 allowlist）下嘗試
      weights_only=True；若因 pickle.UnpicklingError／RuntimeError 失敗，且環境變數
      MISAKA_PM_RVC_STRICT_LOAD 不等於 "1"，則印出＋記錄明確中文警告（含檔案路徑、原始
      錯誤）後退回 weights_only=False；MISAKA_PM_RVC_STRICT_LOAD=1 時改為直接拋出
      RuntimeError、不退回。刻意不 allowlist _make_placeholder_class() 動態產生的
      fork-namespace 佔位類別（理由：這些類別是依屬性名稱即時合成、無法窮舉，且帶有
      __reduce__）——需要它們的 checkpoint 會如預期觸發退回＋警告，而非被錯誤地判定為
      「安全」。_RVCForkFinder 的作用範圍也收斂：新增 _uninstall_rvc_finder()，
      load_rvc_checkpoint() 改為只在單次載入期間安裝該 meta-path finder、載入完（含例外
      路徑）立刻卸載，而非像修復前那樣永久掛在 sys.meta_path 上攔截任何
      ultimate_rvc/infer/lib 具名 import。真實模型驗證（見上方 tests）：站主的
      makima-en-dub.pth 走安全路徑直接成功；yuuka_best.pth 因引用
      ultimate_rvc.typing_extra.TrainingSampleRate 觸發退回，退回後結果與舊版
      weights_only=False 無條件載入完全相同（逐 key／逐 tensor 值比對一致）。README.md
      #security 三語警示同步更新以反映新的預設行為與 MISAKA_PM_RVC_STRICT_LOAD 選項。
      變更檔案：voice/_safe_load.py（新增）、voice/rvc_wrapper.py（_install_rvc_finder
      改為回傳是否為本次呼叫所安裝、新增 _uninstall_rvc_finder／_rvc_safe_globals／
      load_rvc_checkpoint，_load_model 改呼叫 load_rvc_checkpoint）、
      tests/test_rvc_safe_load.py（新增，torch-free）、
      tests/test_rvc_safe_load_torch.py（新增，真 torch，pytest.importorskip 保護）、
      README.md（#security 三語段落）、docs/blueprint/entries/BP-VOICE-1.md（本條目）。
  - date: 2026-09-07
    summary: >-
      待回答 #49 FRESH opus 複核（commit ab25797，worktree `.claude/worktree/rvc-safe-load`）
      裁定 CHANGES-NEEDED：2 medium（F1、F2）、2 low（F3、F4）、1 low/info（F5）、
      2 informational（F6、F7），共 7 項。複核結論與本次修復逐項對應：
      F1（medium）— voice/_safe_load.py:76 原本用
      `except (pickle.UnpicklingError, RuntimeError)` 判斷是否退回，但 torch 對截斷 zip 拋
      RuntimeError、對垃圾位元組拋 UnpicklingError，等同把「檔案損毀」與「檔案含未被允許的
      pickle 全域物件」混為一談——損毀檔案會被誤判為需要退回，因而印出「此模式會執行任意
      程式碼」的警告，且對已損毀檔案多做一次不必要的 weights_only=False unpickle，牴觸模組
      docstring 自己聲明的「只有 weights_only 被拒才觸發退回」。複核以 repro 證實：missing
      file/empty file 因非 pickle 例外原樣拋出（無警告），但 truncated zip/garbage bytes 均誤觸
      退回＋警告。修復：改用 torch.serialization.get_unsafe_globals_in_checkpoint() 靜態掃描（不
      unpickle）先決定，掃描本身失敗（非合法 torch 檔）就原樣往外拋、絕不退回；掃描回傳空清單
      才嘗試 weights_only=True，此時的任何例外也原樣往外拋；掃描回傳非空清單才視為「需要退回」
      並印出含檔名與全域物件名稱的警告（或 strict 模式下拋出）。新增 5 個 torch-free 測試
      （tests/test_rvc_safe_load.py）+ 2 個真 torch 測試（tests/test_rvc_safe_load_torch.py）
      覆蓋：乾淨 checkpoint 僅 weights_only=True 一次、截斷 zip／垃圾位元組直接拋出且
      torch.load 呼叫序列為空且不印警告、含未被允許全域物件的 checkpoint 僅 weights_only=False
      一次、strict 模式下直接拋出並列出全域物件名稱。
      F2（medium）— 複核測出站主 yuuka_best.pth 唯一觸發退回的原因是一個 GLOBAL
      `ultimate_rvc.typing_extra.TrainingSampleRate`，implement.md 原本給的「無法窮舉」「帶
      __reduce__」兩個不 allowlist 的理由經複核逐項反駁：get_unsafe_globals_in_checkpoint()
      可在載入前就列出這個檔案實際需要哪些全域物件（不必事先窮舉整個 fork 命名空間），且
      safe_globals 支援 `(callable, "dotted.path")` 形式，可把任意名稱綁定到我們自己的類別；
      該類別的 `__reduce__` 只是 `cls(str(self))`，在 weights_only 還原時等同呼叫
      `str.__new__`，不是程式碼執行原語。修復：voice/rvc_wrapper.py 新增
      `_StaticForkGlobalPlaceholder`（純 str 子類別，故意不定義 __reduce__/__setstate__，因為
      這個類別只會被「還原進去」、從不會被「pickle 出去」），並在 `_rvc_safe_globals()` 新增
      `_KNOWN_FORK_SAFE_GLOBALS = [(_StaticForkGlobalPlaceholder,
      "ultimate_rvc.typing_extra.TrainingSampleRate")]`——只綁定這一個複核驗證過的名稱，不
      allowlist 整個 fork 命名空間。重新以唯讀 embedded 直譯器驗證：兩個站主真實模型
      （makima-en-dub.pth／yuuka_best.pth）在新 allowlist 下靜態掃描結果均為空清單，兩者現在
      都直接走安全路徑、不印警告，且與舊版 weights_only=False 無條件載入結果逐 key／逐 tensor
      完全相同（457 個 weight key 全部一致）。
      F3（low）— docs/blueprint/entries/BP-VOICE-1.md 舊 tests 記錄寫「既有 62 個 + 7 + 3 =
      65」，62+7+3=72≠65，算術錯誤；複核在 merge-base 重新收集得到 55（test_path_traversal.py
      7 個＋test_origin_guard.py 48 個），55+7+3=65 才對得上。已在上方舊 tests 條目的 result
      內修正為「既有 55 個」。
      F4（low）— voice/_safe_load.py 與 tests/test_rvc_safe_load_torch.py 的 docstring 原本斷言
      「py -3.11 genuinely lacks torch」，複核實測此機器 py -3.11 其實裝有 torch
      2.11.0+cu128，與 embedded 直譯器版本相同，斷言與實測不符。已改為條件敘述（「is NOT
      guaranteed to have torch」），並註明這是「本機當前安裝狀態」而非「本 repo 目標直譯器的
      保證特性」，避免未來 session 誤信一個已被實測推翻的宣稱。
      F5（low/info）— voice/rvc_wrapper.py 的 `_install_rvc_finder`/`_uninstall_rvc_finder` 與
      `safe_globals` allowlist 視窗只在單一執行緒循序載入時正確：`_uninstall_rvc_finder` 會移除
      sys.meta_path 上「所有」`_RVCForkFinder` 而非只移除自己裝的那個，兩條執行緒並行載入時，
      先完成的執行緒可能把仍在使用中的另一條執行緒的 finder 卸掉；`safe_globals` 的允許清單在
      torch 內部是 process-global 狀態，視窗期間會暫時影響同進程內其他無關的
      `torch.load(weights_only=True)` 呼叫。複核判定風險低（allowlist 內容本身皆為 inert 類別，
      見 F6），僅需求補充文件、不需改程式碼。已在 voice/rvc_wrapper.py 模組 docstring 補上
      「Concurrency note」段落，明確聲明單執行緒循序載入的假設。
      F6（informational）— 複核對 allowlist 做敵對稽核：weights_only unpickler 底下能碰到
      allowlisted 類別的三個 opcode（NEWOBJ/REDUCE/BUILD）中，REDUCE 真的會呼叫類別的
      `__init__`（複核以 LayerNorm 實測證實），但逐檔 grep voice/rvc_model.py（16 個
      nn.Module 子類別的 __init__ 本體）未找到 eval/exec/__import__/getattr/setattr/open/os.
      /subprocess/system/pickle/compile/globals/locals/lambda 等危險呼叫，故 REDUCE 最壞情況
      只是例外或過大張量配置（DoS），不是 RCE。純資訊性結論，本次未變更任何程式碼。
      F7（informational）— MISAKA_PM_RVC_STRICT_LOAD 原本只接受完全等於 "1" 的字串，
      `=true`/`=yes`/`=on` 會靜默視為未啟用。已改為
      `{"1","true","yes","on"}`（大小寫不拘、去除前後空白）皆視為啟用；新增 10 組
      parametrize 測試覆蓋大小寫與否定案例。
      修復結果：quality-gates/run.py l0 全綠、0 new findings（[G1] 24 total, 0 new；[G2] 23
      total, 0 new；pytest 82 passed；[G3b] PASS）；embedded 直譯器
      tests/test_rvc_safe_load_torch.py 5 passed；blueprint-build.py --lint 通過。變更檔案：
      voice/_safe_load.py（F1 決策邏輯改寫、F4 docstring 措辭、F7 strict 值比對）、
      voice/rvc_wrapper.py（F2 新增 _StaticForkGlobalPlaceholder／_KNOWN_FORK_SAFE_GLOBALS、F5
      模組 docstring 補充）、tests/test_rvc_safe_load.py（新增 15 個測試）、
      tests/test_rvc_safe_load_torch.py（新增 2 個測試）、docs/blueprint/entries/BP-VOICE-1.md
      （F3 修正既有測試數＋本條目）、README.md（#security 三語段落，反映靜態掃描決策與
      yuuka_best.pth 現況）。
---

## 設計說明

RVC（Retrieval-based Voice Conversion）語音轉換管線,四個節點分工：

| 節點 | 用途 | 輸出 |
|---|---|---|
| `MisakaVCLoadModel` | 載入 `.pth`（可選 `.index`),建立 `RVCConverter` 實例 | `VC_MODEL` |
| `MisakaVCAutoParams` | 分析音訊,建議 `index_rate`/`protect`/建議模型採樣率 | `VC_PARAMS` + 文字報告 |
| `MisakaVCConvertBatch` | 用 `VC_MODEL` 轉換整段音訊 | `AUDIO` + 報告 |
| `MisakaVCAudioInfo` | 純顯示音訊資訊（不轉換） | 文字資訊 |

### `RVCConverter`（`voice/rvc_wrapper.py`，2026-04-26 起 Ultimate-RVC 架構）

不依賴 RVC WebUI 啟動,自建 meta-path finder（`_RVCForkFinder`）攔截 `ultimate_rvc`/`infer`/`lib`
等命名空間的 import,讓 `torch.load()` 能還原 pickle 進去的模型物件,即使執行環境沒裝原始
RVC fork 套件也不會炸（`_make_placeholder_class` 提供彈性 stub）。`convert()` 內建靜音切點
分段與 overlap 拼接（取代原規劃中獨立的 `find_cut_points`/`concat_with_crossfade`，見
SPEC §「已移除死碼」段與 2026-06-20 `a4eaba3` 清理記錄）。

### 自動參數建議（`voice/auto_params.py:analyze_audio`）

依 SNR（訊噪比,`_estimate_snr` 用高低 25/75 百分位 RMS 差估計）與 F0 範圍變異決定建議值：

| SNR | index_rate | protect |
|---|---|---|
| < 20dB（雜訊多） | 0.3 | 0.45 |
| 20–40dB | 0.6 | 0.33 |
| > 40dB（乾淨） | 0.75 | 0.25 |

F0 變異 > 200Hz（日文語音等高變化）時 `protect` 再 +0.05（上限 0.5）。另用
`choose_model_sr()` 依輸入採樣率挑最接近的 RVC 模型版本（32k/40k/48k,避免不必要的向上取樣）。

## 流程

```mermaid
flowchart LR
    A["MisakaVCLoadModel<br/>.pth + 可選 .index"] --> D["VC_MODEL"]
    B["MisakaVCAutoParams<br/>分析音訊 SNR/F0"] --> E["VC_PARAMS"]
    D --> C["MisakaVCConvertBatch"]
    E -.可選接入.-> C
    C --> F["RVCConverter.convert()<br/>（靜音切點分段 + overlap 拼接內建）"]
    F --> G["AUDIO + 轉換報告"]
```

## 安全注意事項（README 已記載，此處對應標註）

**2026-09-07 起已修復（待回答 #49，見下方 qa_log）：** `.pth` 模型現在預設透過
`voice/_safe_load.py:load_checkpoint()`（`voice/rvc_wrapper.py:load_rvc_checkpoint()` 呼叫）先以
`torch.serialization.get_unsafe_globals_in_checkpoint()` 靜態掃描（不 unpickle）決定是否需要
`weights_only=False`：掃描回報「無未被允許全域物件」就只走 `weights_only=True` 安全路徑；掃描
回報有未被允許全域物件才印出＋記錄明確警告（含檔案路徑與物件名稱）並退回舊式
`weights_only=False` 載入；`MISAKA_PM_RVC_STRICT_LOAD=1`（或 `true`/`yes`/`on`，大小寫不拘）
可停用退回、直接拒絕。**同日 FRESH opus 複核（F1–F7）後再修復一輪：** 損毀／截斷／垃圾位元組
檔案現在會在靜態掃描階段直接往外拋例外，絕不誤觸退回、絕不印警告（修復前是攔截例外型別來
判斷，會把單純檔案損毀誤判成需要退回）；`voice/rvc_wrapper.py:_rvc_safe_globals()` 新增一個
明確 review 過的 fork 全域物件 binding（`ultimate_rvc.typing_extra.TrainingSampleRate` →
`_StaticForkGlobalPlaceholder`），使站主 `yuuka_best.pth` 現在也直接走安全路徑、不再需要退回。
以下描述的「反序列化任意 pickle」風險現在僅在下列情況才成立：checkpoint 引用了尚未被逐一
review 並 allowlist 的 fork 全域物件（README `## Security` 段已同步更新三語警示）。
`GET /misaka/rvc_model_list`/`rvc_index_list` 這兩條路由本身只回傳既有檔案清單，不涉及使用者
輸入的路徑，不在 BP-API-1 的 traversal 範疇內。
