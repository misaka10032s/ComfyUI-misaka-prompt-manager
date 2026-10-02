# ComfyUI-misaka-prompt-manager

ComfyUI custom-node plugin (Python + JS) for managing prompt profiles, dynamic prompts, and model assets. Supports profile CRUD, cross-checkpoint × prompt loop/cross-product generation, and voice-conversion nodes (RVC + VoxCPM TTS pipeline).

> Dispatched from @PM: your brief carries a conventions excerpt; follow it, and read a section of the full `D:/backup/CSIA/@PM/.claude/context/cluster-conventions.md` only when your topic is outside the excerpt. Working in this repo without an @PM brief: read the sections of that file your task touches.

## Context index

_(none yet — add files here per @PM taxonomy)_

## Quickstart

**Stack:** Python (ComfyUI custom nodes) + JS (web UI extension)

**Entry point:** `__init__.py` — auto-installs core voice deps, registers all nodes (image nodes from `nodes/image/`, voice nodes from `nodes/voice/`), mounts aiohttp REST routes under `/misaka/`, sets `WEB_DIRECTORY = "js"`.

**How to run:** This plugin is loaded by ComfyUI at startup — not run directly. Place/clone into `ComfyUI/custom_nodes/` and restart ComfyUI (or use Manager "Reload Custom Nodes"). No separate dev server.

**Dependencies:** `requirements.txt` — core audio pipeline (librosa, soundfile, soxr, scipy) auto-installs on first load; RVC inference (pyworld, torchcrepe, faiss) and VoxCPM TTS are optional and must be installed manually (see file for instructions). FFmpeg shared DLLs required on Windows for VoxCPM (not pip-installable).

**Tests:** `tests/test_path_traversal.py` (7 tests, covers the profile path-traversal security fix). **Do NOT run plain `pytest tests/` from the repo root** — this repo lives inside a portable ComfyUI installation whose `pytest.ini` and package layout make that invocation try to import this plugin's real `__init__.py` (pulling in the live ComfyUI host) and fail. Use the exact invocation in `## Dev commands` below, or `quality-gates/run.py g3`.

**Reload after code changes:** restart ComfyUI or use ComfyUI-Manager → Reload.

## Dev commands

```
py -3.11 quality-gates/run.py l0              # G1 lint + G2 typecheck + G3 tests, from repo root
py -3.11 quality-gates/run.py g1               # ruff lint only (baselined)
py -3.11 quality-gates/run.py g2               # mypy typecheck only (baselined)
py -3.11 quality-gates/run.py g3               # pytest (7 tests) + assertion-presence on new tests
py -3.11 quality-gates/run.py g1 --update-baseline   # deliberate cleanup / accepted new debt only
py -3.11 quality-gates/run.py g2 --update-baseline
```

Always use `py -3.11` (or the equivalent `python.exe` full path) — **never bare `python`/ `python3`** (a Microsoft Store stub on this machine's PATH), and **never the portable ComfyUI install's own bundled Python** — the gates run in a standalone interpreter deliberately, so mypy/ruff analyze this repo's code without the live ComfyUI host's own config or deps leaking in. The pre-commit hook wires `l0` into `git commit` automatically for any commit that stages `.py` files — activation and its per-clone caveat: `**Hook:**` under `## Code quality gates` below.

## Code quality gates

**L0 only — deliberately, not a partial rollout.** This repo carries exactly ONE test file (`tests/test_path_traversal.py`, 7 tests). Diff coverage (L1) and mutation testing (L2) are theatre, not signal, at that test count — there is nothing for a coverage/mutation gate to meaningfully measure against. If the test suite grows substantially, re-evaluate L1 as a separate, deliberate decision — do not silently expand this recipe.

**Gates shipped:**
- **G1 — ruff lint, baselined** (`quality-gates/check_ruff_baseline.py`). Rule set is ruff's own stable defaults, stated explicitly (`[tool.ruff.lint] select = ["E4","E7","E9","F"]` in `pyproject.toml`) — deliberately NOT the ComfyUI host's own `pyproject.toml` (which enables `T20`/`W29x` and produces 84 findings, mostly `print`-found noise from this plugin's normal console-feedback style). Ruff stops its upward config search at the first `pyproject.toml` it finds, so this repo's own file (committed at repo root) always wins over the host's, in the main tree or any worktree.
- **G2 — mypy typecheck, baselined** (`quality-gates/check_mypy_baseline.py`). Host-provided modules injected by the ComfyUI runtime — never resolvable in a bare interpreter — are `ignore_missing_imports`, not baselined: `comfy`/`comfy.*`, `folder_paths`, `server`. Optional manual-install RVC/TTS deps get the same treatment: `voxcpm`, `transformers`, `pyworld`, `faiss`, `sounddevice`. Always-auto-installed core audio deps that simply ship no type stubs upstream (`soundfile`, `soxr`, `scipy`) are silenced the same way — see `pyproject.toml` -> `[[tool.mypy.overrides]]` for the exact, documented list.
- **G3 — pytest green + G3b assertion-presence on new/changed tests** (`quality-gates/check_test_assertions.py`, diff-scoped AST walk — bolting a zero-assertion check onto the WHOLE repo would also flag any pre-existing offenders, a different problem).
- **`l0` runner** (`quality-gates/run.py`) sequences G1 → G2 → G3, stops on first failure.

**Baselines (version-controlled, by exact identity — never a bare count):** `quality-gates/ruff-baseline.json` (24 unique pre-existing violations; 39 raw findings before dedup — several files repeat the identical file+code+message, e.g. `__init__.py`'s 7× `E402`, `voice/rvc_model.py`'s 5× `E741 Ambiguous variable name: l`), `quality-gates/ mypy-baseline.json` (23 unique pre-existing errors; 24 raw before dedup). This gate does NOT fix either backlog, it only stops NEW findings from landing. `--update-baseline` is for a deliberate, reviewed cleanup or knowingly accepted new debt, never a blanket bypass. Three of the 23 mypy baseline entries (`__init__.py|import-not-found|...__main__.nodes.*`) are a structural artifact of checking this plugin's entrypoint `__init__.py` outside the real `custom_nodes` package context ComfyUI's own loader gives it at runtime (its relative imports resolve fine there) — not a real bug in the file; baselined like everything else rather than engineered around.

**Test-runner quirk (load-bearing, do not "simplify" G3's invocation):** this repo's own root `__init__.py` sits directly above `tests/`. Any `__init__.py`-bearing ancestor directory on the path pytest walks becomes a `Package` collector node, and pytest UNCONDITIONALLY imports that directory's `__init__.py` during `Package.setup()` — independent of `--import-mode`. That means a plain `pytest tests/` (or `pytest` from the repo root) tries to import this plugin's REAL entrypoint, which does `import comfy.sd` and pulls in the live ComfyUI host, breaking on whatever that live install's own optional modules are missing. Running pytest with `cwd=tests/` and explicit `--rootdir=. --confcutdir=.` (exactly what `quality-gates/run.py g3` does) stops the ancestor walk at `tests/` itself (which has no `__init__.py`), so no `Package` node for the repo root is ever built and `__init__.py` is never imported by pytest.

**Scratch/generated exclusions (never a gate input):** `pyproject.toml`'s ruff `exclude` and mypy's `files` allow-list both skip `__pycache__/`, `.claude/` (worktrees + settings), `misaka_node.py.bak`, `.mypy_cache/`, `.ruff_cache/` — mirrored into `.gitignore` and `.graphifyignore`. `js/` and `voice/realtime_stream.py`'s multiprocessing path are covered by G1/G2 like any other tracked `.py`; `js/` itself has no JS-family gate here (out of L0 scope — this recipe is Python-only, per the cluster's Python-family recipe).

**Hook:** `.githooks/pre-commit` runs `quality-gates/run.py l0` whenever a commit stages `.py` files, printing a `checked: N | skipped: …` summary either way. **Activation:** `core.hooksPath` is per-clone LOCAL config (it lives in `.git/config`, never in a tracked file), so it is NOT self-installing: every fresh clone or new machine runs without the guard until this command is run again:
```
git config core.hooksPath .githooks
```
Known gaps: a detached HEAD and `git commit --no-verify` skip the hook; it is not a complete gate. `git ls-files -s .githooks/pre-commit` must report `100755` — a non-executable hook is silently skipped on POSIX; `.gitattributes` forces `eol=lf` on that one file so Windows' `core.autocrlf` never reintroduces CRLF into a script `sh` has to parse.

**Interpreter:** all measurements and the gate itself run under `py -3.11` (`C:/Users/natsume_saiko/AppData/Local/Programs/Python/Python311/python.exe`) — the machine's standard Python 3.11, NOT the portable ComfyUI installation's bundled interpreter. ruff 0.15.12 and mypy 1.20.2 are already present there.

## Domain notes

- Node registration: `__init__.py` merges `nodes/image` and `nodes/voice` mappings.
- Profile storage path: resolved via `nodes/image/factory.get_storage_path()`.
- Voice spec: `docs/superpowers/specs/SPEC-voice-conversion.md`; voice implementation under `voice/`.
- Realtime streaming nodes (`voice/realtime_stream.py`) are NOT registered in `__init__.py` — blueprint/prototype only; do not delete without checking the roadmap task first.
- `convert_workflows.py`: standalone migration tool (no ComfyUI dependency at import).
- Same-origin guard + request-body size cap for `/misaka/*` write routes: `nodes/image/factory/_origin_guard.py` (see `docs/blueprint/entries/BP-IMG-1.md` qa_log). No open security task tracked in the registry at this time.
