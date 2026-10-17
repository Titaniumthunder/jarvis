# Jarvis — Build Progress

---

## Local-First, Cloud-Augmented Stack

Jarvis runs locally on a Mac M5 Pro and stores all your data on disk. Two cloud
APIs are used by default for speed, and every cloud LLM call falls back to a
local model if it fails.

**Local components** (run on your machine, no network calls):
- **Ollama + Gemma4** — offline fallback for every cloud LLM call, and the only vision model (image-guided Blender generation).
- **Whisper (base)** — voice transcription (needs `ffmpeg` to decode recordings)
- **SDXL-Turbo** — text → image (MPS, ~2 s)
- **TripoSR** — image → 3D mesh (CPU, ~15 s)
- **Obsidian vault** — long-term memory in a `Jarvis Memory` folder next to the repo (`JARVIS_MEMORY_VAULT` overrides)
- **Blender + MCP socket** — local 3D modelling, no cloud calls
- **Interaction logger** — training data for the future LoRA fine-tune, written to `training_data/`
- **macOS `say`** — text-to-speech

**Cloud components** (behind API keys):
- **Groq** — `gpt-oss-20b` for brain routing (`brain.py`), `gpt-oss-120b` for agents (via `llm_tool.py`). Every call falls back to Ollama+Gemma4 if it fails. Free tier: 8,000 tokens/min and 1,000 requests/day per model; the ~2,700-token brain prompt limits routing to about 3 requests a minute before Groq backs off.
- **Brave Search API** — used by `search_tool.py` for web search. Required for the `web_search` action; without it, web search is disabled but every other action still works.

---

## Privacy & Offline Mode

Your data stays local: memory, generated files, and training data are all
written to disk on this Mac. What leaves the machine is the text of each
request (to Groq) and search queries (to Brave).

Offline behaviour today:
- If a Groq call fails at runtime (network down, rate limit, outage), the brain and every agent fall back to Ollama+Gemma4 automatically, and routing still picks the right action.
- **Known gap:** `GROQ_API_KEY` must still be set for Jarvis to start — `tools/groq_tool.py` raises at import without it. A keyless, fully offline start needs that check moved to call time.
- Without `BRAVE_API_KEY`, only `web_search` stops working.

---

## Phase 12 — Training-data logger & cleanup ✅ COMPLETE (Sep 2026)
- **Interaction logger** (`tools/interaction_logger.py`) — every turn from the web UI and CLI is logged as JSONL training data for a future LoRA fine-tune. Corrections ("no, I meant…") label the previous turn negative, praise labels it positive, and `clarify`/`unknown` turns label themselves. A queue plus a daemon thread keep it off the request path (~9 µs per call). `./jarvis --stats` shows progress toward the 500-turn target.
- **Groq model swap** — `llama-3.3-70b-versatile` was retired. Brain routing now uses `gpt-oss-20b` and agents use `gpt-oss-120b` (a bug had silently given agents the 20b; `llm_tool` now forwards the model). Token budgets were raised because gpt-oss reasoning tokens count against `max_tokens`.
- **Memory vault path fix** — memory reads and writes had been going to a non-existent `~/Documents/Jarvis Memory`; they now use the real vault.
- **Bug fixes** — image-guided Blender generation sent a Groq model name to Ollama (404) and now uses Gemma4; the server's static mounts no longer depend on the working directory, so a fresh clone starts; Brave's `<strong>` markup no longer leaks into search answers.
- **Cleanup** — one shared `strip_fences()` helper; the Ollama endpoint and model are defined once; `diagram_agent` goes through `llm_tool` like every other agent (and gains the Ollama fallback); the unreachable `terminal_tool.py` and unused imports are gone.

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
- ❌ Removed `gemini_tool.py` (the Gemini backend was no longer used)
- ❌ Removed `terminal_tool.py` (never imported — `run_command` uses computer_agent's own blocklist)

---

## Models

| Model | Size | Used for | Speed |
|---|---|---|---|
| `gpt-oss-20b` (Groq) | cloud | Brain routing | ~0.4 s when not rate-limited |
| `gpt-oss-120b` (Groq) | cloud | Agents: answers, code, diagrams, search summaries | ~0.7 s when not rate-limited |
| `gemma4:latest` | 9.6GB | Offline fallback + vision | 66 tok/sec (Metal) |
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

## Full action library (25 actions)

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

---

## What's left

### Software
- [ ] Wake word detection ("Hey Jarvis")
- [ ] Voice mode in browser (mic button + Whisper)
- [ ] Command history (up arrow in chat)
- [ ] TTS in browser (Jarvis speaks back)
- [ ] Markdown rendering in chat bubbles
- [ ] Keyless offline start (move the Groq key check to call time)
- [ ] LoRA fine-tune on logged turns (gated on 500 turns — `./jarvis --stats`)

### Hardware
- [ ] Robot arm (servos + PCA9685 + Arduino + YOLO)
- [ ] Bambu printer camera (RTSP stream)
- [ ] Print failure detection (YOLO)
- [ ] Bambu Studio auto-open STL files
