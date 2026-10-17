# Jarvis

A local-first AI desktop assistant for macOS — voice or text in, action out.

## Overview

Jarvis takes voice or text input, routes it through an LLM brain, and dispatches the request to one of 25 actions handled by specialist agents. Those agents produce real outputs: 2D images via SDXL-Turbo, 3D meshes via TripoSR, live 3D models in Blender (over an MCP socket), web search summaries, generated code, Mermaid diagrams, persistent notes in an Obsidian vault, and a simulated 7-DOF Franka Panda arm that stacks blocks in MuJoCo. It runs on a Mac (Apple Silicon). Groq's cloud models handle fast inference; Ollama + Gemma4 runs locally, takes over automatically whenever a Groq call fails, and handles image understanding. Every interaction is also logged locally as training data for a future on-device LoRA fine-tune.

## Demo

> Demo video coming soon.

## Architecture

Voice from the mic (Whisper) or text from the web UI feeds into [`brain.py`](brain.py), which asks the LLM to emit a structured JSON action drawn from a fixed library. Groq (`gpt-oss-20b`) is the routing model, with Ollama+Gemma4 as a transparent fallback; the JSON is validated against `KNOWN_ACTIONS` before anything else runs. [`orchestrator.py`](orchestrator.py) routes the validated action to a specialist agent, which uses small, single-purpose tools in `tools/` to do the actual work and returns a string the server can stream back. Every turn is also handed to [`tools/interaction_logger.py`](tools/interaction_logger.py), which records it as training data off the request path. An interactive architecture diagram lives at [`static/diagram.html`](static/diagram.html) — open it directly in a browser.

## Local-first, cloud-augmented

Everything that touches your data runs locally: voice, image and 3D generation, Blender, the Obsidian memory vault, the arm sim, and the training-data logger. The only cloud calls are LLM inference (Groq) and web search (Brave).

- **Groq** — `gpt-oss-20b` routes every request; agents write code and prose with `gpt-oss-120b`.
- **Ollama + Gemma4** — takes over automatically whenever a Groq call fails, and handles image understanding (Groq's models are text-only).
- **Brave** — only used by the `web_search` action.

Known limitations:

- **`GROQ_API_KEY` is currently required to start.** `tools/groq_tool.py` raises at import without it. Runtime Groq failures fall back to Ollama as intended, but a keyless, fully offline start does not work yet.
- **Groq's free tier allows about 3 messages a minute.** It caps each model at 8,000 tokens/min and 1,000 requests/day, and the brain's system prompt alone is ~2,700 tokens. Past that pace, requests slow to 10–20 s while Groq backs off, or fall back to Ollama.

## What it can do

| Action | Agent | Status |
|---|---|---|
| `get_time` | computer | ✅ |
| `search_files` | computer | ✅ |
| `web_search` | computer | ✅ Brave Search + LLM summary |
| `open_in_browser` | computer | ✅ |
| `run_command` | computer | ✅ |
| `generate_image` | cad | ✅ SDXL-Turbo, click to expand |
| `generate_cad` | cad | ✅ Three.js preview |
| `generate_shape_e` | cad | ✅ TripoSR pipeline |
| `open_bambu` | cad | ⬜ STUB |
| `generate_blender_mcp` | blender_mcp | ✅ Image-guided (SDXL → Gemma4 vision → bpy) |
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
| `move_arm` | arm | ✅ Simulated Franka Panda stacks 3 blocks (MuJoCo) |
| `reset_blocks` | arm | ✅ Re-spawns the demo blocks at random positions |
| `clarify` | none | ✅ |
| `unknown` | none | ✅ |

## Setup

### Prerequisites

- macOS (Apple Silicon recommended)
- Python 3.11+ for the main venv
- Python 3.10 for the separate MuJoCo arm-sim venv (see [`docs/ARM_SETUP.md`](docs/ARM_SETUP.md))
- Ollama installed (`brew install ollama`) with `gemma4:latest` pulled
- `ffmpeg` (`brew install ffmpeg`) for voice mode — Whisper uses it to decode the recording
- Blender with the Blender MCP add-on enabled (for `generate_blender_*` actions). Add-ons are installed per Blender version, so enable it in the same version `JARVIS_BLENDER_PATH` launches.

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

Then edit `.env`. `GROQ_API_KEY` is required (see the known limitations above); `BRAVE_API_KEY` is only needed for web search. Get them at:

- Groq: https://console.groq.com/keys
- Brave Search: https://api-dashboard.search.brave.com/app/keys

Optional overrides — Blender path, Claude CLI path, memory vault, training-data location — are documented in [`.env.example`](.env.example).

### Simulated robot arm (optional)

See [`docs/ARM_SETUP.md`](docs/ARM_SETUP.md). Requires a separate Python 3.10 venv at `~/mujoco-venv` because MuJoCo wheels don't yet exist for newer Python versions.

## Run

```bash
./jarvis-web      # Browser UI at localhost:7777
./jarvis          # Voice mode (mic + Whisper)
./jarvis --text   # Terminal mode
./jarvis --silent # Terminal mode, no spoken replies
./jarvis --stats  # Training data collected so far
```

Set `JARVIS_DEV=1` before `./jarvis-web` to auto-reload the server when you edit code.

## Tech stack

- Brain: Groq `gpt-oss-20b` (cloud) / Ollama Gemma4 (local fallback)
- Agents: Groq `gpt-oss-120b` (cloud) / Ollama Gemma4 (local fallback)
- Vision: Ollama Gemma4 (local)
- Voice: OpenAI Whisper base
- Image gen: SDXL-Turbo on MPS
- Image → 3D: TripoSR
- 3D editor: Blender via MCP socket on port 9876
- Robot arm: MuJoCo + Franka Panda from `mujoco_menagerie`
- Web UI: FastAPI + SSE streaming
- Memory: Obsidian vault — a `Jarvis Memory` folder next to the repo (override with `JARVIS_MEMORY_VAULT`)
- Training data: append-only JSONL in `training_data/` (override with `JARVIS_TRAINING_DATA`)

## Project status

Working today: voice and text input, the full 25-action pipeline, the web UI with SSE streaming, and a simulated Franka Panda that stacks three blocks. Every interaction is logged as training data toward a first LoRA fine-tune (target: 500 turns — check with `./jarvis --stats`). Stubs: physical arm hardware (the arm runs in simulation only), printer camera (`watch_printer`), Bambu Studio integration (`open_bambu`).

## License

> License: TBD
