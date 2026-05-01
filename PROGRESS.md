# Jarvis — Build Progress

---

## Local-First, Cloud-Augmented Stack

Jarvis runs locally on a Mac M5 Pro and stores all your data on disk. For
inference speed it uses two cloud APIs by default, but every cloud call has a
local fallback so the assistant keeps working with no internet and no API keys.

**Local components** (run on your machine, no network calls):
- **Ollama + Gemma4** — brain reasoning, agent calls, search summarisation. Offline fallback for every cloud LLM call.
- **Whisper (base)** — voice transcription
- **SDXL-Turbo** — text → image (MPS, ~2 s)
- **TripoSR** — image → 3D mesh (CPU, ~15 s)
- **Obsidian vault** — long-term memory at `~/Documents/Jarvis Memory/`
- **Blender + MCP socket** — local 3D modelling, no cloud calls
- **macOS `say`** — text-to-speech

**Cloud components** (optional, behind API keys):
- **Groq (Llama 3.3 70B)** — primary fast LLM in `brain.py`, `llm_tool.py`, and `diagram_agent.py`. Used for low-latency replies. Falls back to Ollama+Gemma4 if `GROQ_API_KEY` is unset or the call fails.
- **Brave Search API** — used by `search_tool.py` for web search + AI summary. Required for the `web_search` action; with no key, web search is disabled but every other action still works.
- **Gemini 2.0 Flash** — legacy `gemini_tool.py`, kept as an alternate LLM backend. Not on the default code path.

---

## Privacy & Offline Mode

With **all three API keys left blank** in `.env`, Jarvis is fully offline:
- The brain runs on Ollama+Gemma4 (slower but private).
- All agent calls fall back to Ollama+Gemma4.
- Voice, image-gen, 3D-gen, Blender, memory, and code agents already run locally — they don't change.
- Only the `web_search` action stops working (Brave is required for that).

The cloud calls are a **speed optimization, not a requirement.** If you want
zero network egress, leave the keys empty and Jarvis will still answer
questions, generate images, build 3D models, write code, and remember things
— all from your local machine.

---

## Phase 11 — Cleanup pass ✅ COMPLETE (April 2026)
- **Security:** three hardcoded API keys (Gemini, Brave, Groq) moved to `os.environ`; `.webui_secret_key` deleted; `.env.example` documents the keys and is the only template that ships.
- **Path portability:** new `tools/paths.py` is the single source of truth; every hardcoded `/Users/alexsalamati/...` path was removed from tools, agents, and the brain's system prompt. External binaries (`Blender`, `claude` CLI) read from `JARVIS_BLENDER_PATH` / `JARVIS_CLAUDE_CLI` with Mac defaults.
- **Dead code:** removed duplicate `file_tools.py` / `terminal_tools.py`, placeholder `openscad_tool.py` / `bambu_tool.py`, and the `get_info` action alias; experimental scripts moved to `archive/`.
- **MuJoCo arm:** `move_arm` is no longer a stub — `tools/arm_sim_server.py` runs the Franka Panda in `~/mujoco-venv` via `mjpython`, `tools/arm_sim_client.py` auto-launches it from the main venv, and `agents/arm_agent.py` implements `pick_up` / `place` / `point_at` / `home`.
- **Onboarding:** `README.md`, `requirements.txt`, `requirements-mujoco.txt`, and `docs/ARM_SETUP.md` added; `python-dotenv` auto-loads `.env` in `server.py` and `main.py`.

---

## Phase 3 — Core Brain & Voice ✅ COMPLETE
- `brain.py` — Ollama + Gemma4, structured JSON, validates against action library
- `listen.py` — Whisper base model, mic recording + transcription
- `orchestrator.py` — routes actions to agents
- `main.py` — voice + text + silent mode, clarification loop
- `tts_tool.py` — Jarvis speaks replies via macOS `say`
- `llm_tool.py` — shared Ollama helper, text + image (multimodal) support
- `computer_agent.py` — run_command, search_files, web_search, open_in_browser

---

## Phase 4 — 3D Generation ✅ COMPLETE
- `html_preview_tool.py` — Three.js rotatable browser preview
- `shape_tool.py` — 18 hardcoded revolution profiles + LLM fallback with cone validator
- `blender_tool.py` — saves bpy script, opens Blender (used by TripoSR pipeline)
- `image_gen_tool.py` — SDXL-Turbo on MPS float32, ~2s per image
- `triposr_tool.py` — image → 3D mesh via TripoSR + rembg background removal

---

## Phase 5 — Intelligence & Search ✅ COMPLETE
- `search_tool.py` — Google search, top 5 results → Ollama summarises
- `knowledge_agent.py` — 3-tier: capabilities → LLM knowledge → Google fallback
- Clarification system with smart best-guess

---

## Phase 6 — Web UI ✅ COMPLETE
- FastAPI server on `http://localhost:7777`
- Iron Man dark theme, SSE word-by-word streaming
- Card system: time, files, search, image, 3D, code file, clarify
- Heartbeat watchdog, auto-shutdown on tab close
- `./jarvis-web` launcher with `--reload` for development

---

## Phase 7 — Code Agent ✅ COMPLETE
- `file_tool.py` — read/write/list files (home directory only)
- `terminal_tool.py` — run shell commands, block destructive patterns
- `code_agent.py` — write_code, edit_file, explain_code

---

## Phase 8 — Blender MCP ✅ COMPLETE
- `blender_mcp_tool.py` — TCP socket client to Blender MCP server (port 9876)
- Auto-launches Blender + auto-connects MCP addon on first request
- `blender_mcp_agent.py` — image-guided generation (SDXL → Gemma4 vision → bpy)
- Session memory — saves last code + reference image for refinements
- Auto-retry with error fixing (up to 3 attempts)

---

## Phase 9 — Memory (Obsidian) ✅ COMPLETE
- `memory_agent.py` — reads/writes to `~/Documents/Jarvis Memory/` vault
- `remember` action — saves facts, preferences, project notes
- `recall` action — searches vault, LLM formats natural language answer
- Auto-injects relevant memories into knowledge agent before every answer
- Auto-memory: background task after every chat extracts facts worth saving
- Vault structure: preferences.md, facts.md, projects/, people/, conversations/

---

## Phase 10 — Quality & UX improvements ✅ COMPLETE
- **Claude Code Blender agent** (`blender_claude_agent.py`) — uses `/usr/local/bin/claude -p` as sub-agent for high-quality bpy code; auto-retry on error; session memory for refinements. Default for all Blender requests.
- **Image lightbox** — click any generated image to expand fullscreen; Esc to close
- **Inline code display** — code renders in chat with filename header + Copy button (like Claude)
- **Adaptive response length** — short answers for simple questions, bullets for complex
- **Web search fixed** — DDG news search for news queries (real article summaries); page scraping for top article; fallback snippets. Answer streams in bubble, sources in card as clickable links.
- **Search engine** — DuckDuckGo (`ddgs`) replaces broken Google scraper (Google now blocks all Python scrapers with JS challenges)

---

## Cleanup done
- ❌ Removed `shape_e_tool.py` (replaced by TripoSR)
- ❌ Removed `generate_blender` action (replaced by `generate_blender_mcp` / `generate_blender_cc`)
- ❌ Removed `_generate_blender()` from cad_agent.py
- ❌ Deleted `shap_e_model_cache/` → freed **4.9GB** of disk space

---

## Models

| Model | Size | Used for | Speed |
|---|---|---|---|
| `gemma4:latest` | 9.6GB | Brain + all agents | 66 tok/sec (Metal) |
| `gemma4:31b` | 20GB | Available, not default | 0.7 tok/sec |
| Whisper base | 140MB | Voice transcription | fast |
| SDXL-Turbo | 7GB | Text → image | ~2s (MPS) |
| TripoSR | 1.2GB | Image → 3D mesh | ~15s (CPU) |
| rembg u2net | 176MB | Background removal | fast |
| Claude Code CLI | — | Blender code sub-agent | via `/usr/local/bin/claude` |

---

## How to start

```bash
cd "/Users/alexsalamati/Personal Project/Desktop assistant/jarvis"
./jarvis-web          # opens http://localhost:7777
```

---

## Full action library (24 actions)

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

---

## What's left

### Software
- [ ] Wake word detection ("Hey Jarvis")
- [ ] Voice mode in browser (mic button + Whisper)
- [ ] Command history (up arrow in chat)
- [ ] TTS in browser (Jarvis speaks back)
- [ ] Markdown rendering in chat bubbles

### Hardware
- [ ] Robot arm (servos + PCA9685 + Arduino + YOLO)
- [ ] Bambu printer camera (RTSP stream)
- [ ] Print failure detection (YOLO)
- [ ] Bambu Studio auto-open STL files
