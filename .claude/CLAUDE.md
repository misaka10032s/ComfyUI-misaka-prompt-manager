# ComfyUI-misaka-prompt-manager

ComfyUI custom-node plugin (Python + JS) for managing prompt profiles, dynamic prompts, and
model assets. Supports profile CRUD, cross-checkpoint × prompt loop/cross-product generation,
and voice-conversion nodes (RVC + VoxCPM TTS pipeline).

> Cluster conventions (git authority, language, i18n, ports, layout) are BINDING and live at
> D:/backup/CSIA/@PM/.claude/context/cluster-conventions.md — Read it before any work here.

## Delegation & verification

- Orchestration, model tiering, and dispatch rules: D:/backup/CSIA/@PM/.claude/context/model-dispatch-doctrine.md
- Decision rubrics (escalate / done / ask / change course): D:/backup/CSIA/@PM/.claude/context/judgment-rubrics.md
- Whoever produced work never certifies it — verification runs in a fresh-context agent.
- Every done/correct/dead/broken claim carries evidence: file:line, test output, or read-back.
- Target missing or contradicting the task → STOP and ask; never scaffold around it.

## Context index

_(none yet — add files here per @PM taxonomy)_

## Quickstart

**Stack:** Python (ComfyUI custom nodes) + JS (web UI extension)

**Entry point:** `__init__.py` — auto-installs core voice deps, registers all nodes
(image nodes from `nodes/image/`, voice nodes from `nodes/voice/`), mounts
aiohttp REST routes under `/misaka/`, sets `WEB_DIRECTORY = "js"`.

**How to run:** This plugin is loaded by ComfyUI at startup — not run directly.
Place/clone into `ComfyUI/custom_nodes/` and restart ComfyUI (or use Manager
"Reload Custom Nodes"). No separate dev server.

**Dependencies:** `requirements.txt` — core audio pipeline (librosa, soundfile, soxr,
scipy) auto-installs on first load; RVC inference (pyworld, torchcrepe, faiss) and
VoxCPM TTS are optional and must be installed manually (see file for instructions).
FFmpeg shared DLLs required on Windows for VoxCPM (not pip-installable).

**Tests:** `pytest tests/` from repo root. Currently: `tests/test_path_traversal.py`
(covers the profile path-traversal security fix).

**Reload after code changes:** restart ComfyUI or use ComfyUI-Manager → Reload.

## Domain notes

- Node registration: `__init__.py` merges `nodes/image` and `nodes/voice` mappings.
- Profile storage path: resolved via `nodes/image/factory.get_storage_path()`.
- Voice spec: `SPEC-voice-conversion.md`; voice implementation under `voice/`.
- Realtime streaming nodes (`voice/realtime_stream.py`) are NOT registered in `__init__.py`
  — blueprint/prototype only; do not delete without checking the roadmap task first.
- `convert_workflows.py`: standalone migration tool (no ComfyUI dependency at import).
- Open security task: `get_project` path-traversal on `project_id` — tracked in registry.
