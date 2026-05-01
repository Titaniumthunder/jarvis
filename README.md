# Jarvis

A local-first AI desktop assistant for macOS — voice or text in, action out.

## Overview

Jarvis takes voice or text input, routes it through a local-first LLM brain, and dispatches the request to one of 24 actions handled by specialist agents. Those agents produce real outputs: 2D images via SDXL-Turbo, 3D models in Blender (built live over an MCP socket), web search summaries, generated code, Mermaid diagrams, persistent notes in an Obsidian vault, and simulated motion of a 7-DOF Franka Panda arm in MuJoCo. It runs on a Mac (Apple Silicon) and uses Ollama + Gemma4 for fully offline operation; cloud LLMs (Groq for fast inference, Gemini as a backup) are optional speed boosters that the system falls back away from automatically.

## Demo

> Demo video coming soon.

## Architecture

Voice from the mic (Whisper) or text from the web UI feeds into [`brain.py`](brain.py), which asks the LLM to emit a structured JSON action drawn from a fixed library. Groq (Llama 3.3 70B) is the primary LLM with Ollama+Gemma4 as a transparent fallback; the JSON is validated against `KNOWN_ACTIONS` before anything else runs. [`orchestrator.py`](orchestrator.py) routes the validated action to a specialist agent, which uses small, single-purpose tools in `tools/` to do the actual work and returns a string the server can stream back. An interactive architecture diagram lives at [`static/diagram.html`](static/diagram.html) — open it directly in a browser.

## Local-first, cloud-augmented

With **all three API keys left blank** in `.env`, Jarvis runs fully offline:

- The brain runs on Ollama+Gemma4 (slower, but private).
- Every agent call falls back to Ollama+Gemma4.
- Voice, image generation, 3D generation, Blender, memory, code, and arm-sim all run locally — nothing changes.
- Only the `web_search` action stops working (Brave is required for that).

The cloud calls are a **speed optimization, not a requirement.**

## What it can do

| Action | Agent | Status |
|---|---|---|
| `get_time` | computer | ✅ |
| `search_files` | computer | ✅ |
| `web_search` | computer | ✅ Brave Search + Ollama summary |
| `open_in_browser` | computer | ✅ |
| `run_command` | computer | ✅ |
| `generate_image` | cad | ✅ SDXL-Turbo, click to expand |
| `generate_cad` | cad | ✅ Three.js preview |
| `generate_shape_e` | cad | ✅ TripoSR pipeline |
| `open_bambu` | cad | ⬜ STUB |
| `generate_blender_mcp` | blender_mcp | ✅ Gemma4, image-guided |
| `refine_blender_mcp` | blender_mcp | ✅ Session memory |
| `generate_blender_cc` | blender_cc | ✅ Claude Code sub-agent (default) |
| `refine_blender_cc` | blender_cc | ✅ Claude Code refinement |
| `answer_question` | knowledge | ✅ LLM + web fallback |
| `write_code` | code | ✅ Inline display with Copy |
| `edit_file` | code | ✅ Inline display with Copy |
| `explain_code` | code | ✅ |
| `remember` | memory | ✅ Obsidian vault |
| `recall` | memory | ✅ Natural language answer |
| `generate_diagram` | diagram | ✅ Mermaid.js (flowcharts, logic gates) |
| `watch_printer` | vision | ⬜ STUB (hardware needed) |
| `move_arm` | arm | ✅ Simulated Franka Panda (MuJoCo) |
| `clarify` | none | ✅ |
| `unknown` | none | ✅ |

## Setup

### Prerequisites

- macOS (Apple Silicon recommended)
- Python 3.11+ for the main venv
- Python 3.10 for the separate MuJoCo arm-sim venv (see [`docs/ARM_SETUP.md`](docs/ARM_SETUP.md))
- Ollama installed (`brew install ollama`) with `gemma4:latest` pulled
- Blender installed (for `generate_blender_*` actions)

### Install

```bash
git clone https://github.com/<user>/jarvis.git
cd jarvis
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Configure

```bash
cp .env.example .env
```

Then edit `.env`. All three API keys are **optional** — Jarvis falls back to local Ollama if any are missing. Get them at:

- Groq: https://console.groq.com/keys
- Gemini: https://aistudio.google.com/apikey
- Brave Search: https://api-dashboard.search.brave.com/app/keys

### Simulated robot arm (optional)

See [`docs/ARM_SETUP.md`](docs/ARM_SETUP.md). Requires a separate Python 3.10 venv at `~/mujoco-venv` because MuJoCo wheels don't yet exist for newer Python versions.

## Run

```bash
./jarvis-web      # Browser UI at localhost:7777
./jarvis          # Voice mode (mic + Whisper)
./jarvis --text   # Terminal mode
./jarvis --silent # Terminal mode, no spoken replies
```

## Tech stack

- Brain: Groq Llama 3.3 70B (cloud) / Ollama Gemma4 (local fallback)
- Voice: OpenAI Whisper base
- Image gen: SDXL-Turbo on MPS
- Image → 3D: TripoSR
- 3D editor: Blender via MCP socket on port 9876
- Robot arm: MuJoCo + Franka Panda from `mujoco_menagerie`
- Web UI: FastAPI + SSE streaming
- Memory: Obsidian vault at `~/Documents/Jarvis Memory/`

## Project status

Phases 1–6 cleanup just completed (April 2026). Working today: voice and text input, full 24-action pipeline, web UI with SSE streaming, simulated 7-DOF Franka Panda arm. Stubs: physical arm hardware (`move_arm` works in sim, no servos yet), printer camera (`watch_printer`), Bambu Studio integration (`open_bambu`).

## License

> License: TBD
