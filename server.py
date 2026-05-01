from dotenv import load_dotenv
load_dotenv()

# server.py
# FastAPI backend for the Jarvis browser UI.
#
# Exposes the full Jarvis pipeline (brain → orchestrator → agents) as an HTTP API.
# The browser sends a message, the server runs it through Jarvis, and streams
# the reply back word-by-word using Server-Sent Events (SSE).
#
# Endpoints:
#   GET  /              → serves the chat UI (index.html)
#   GET  /health        → returns ollama status
#   POST /chat          → runs a message through Jarvis, returns stream_id + metadata
#   GET  /stream/{id}   → SSE stream of word tokens + card payload
#   POST /heartbeat     → browser pings every 15s so server knows tab is still open
#   POST /shutdown      → called by browser on tab close, kills ollama

import os
import sys
import asyncio
import time
import uuid
import json
import queue
import subprocess
import requests as req
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Add jarvis root to path so we can import brain, orchestrator etc.
sys.path.insert(0, str(Path(__file__).parent))
import brain
import orchestrator

# ── App setup ────────────────────────────────────────────────────────────────
app = FastAPI(title="Jarvis")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static",   StaticFiles(directory="static"),          name="static")
app.mount("/previews", StaticFiles(directory="previews"),         name="previews")
app.mount("/images",   StaticFiles(directory="image_gen_output"), name="images")

# ── State ─────────────────────────────────────────────────────────────────────
OLLAMA_PROC      = None          # Popen handle if WE started ollama
LAST_HEARTBEAT   = time.time()   # updated every 15s by the browser
STREAMS: dict    = {}            # stream_id → queue of SSE events
HEARTBEAT_TIMEOUT = 60           # seconds before assuming browser closed

# Rolling conversation buffer for auto-memory extraction
# Keeps last 10 exchanges so the memory agent has context
CONVERSATION_BUFFER: list = []
MAX_BUFFER = 10


# ── Ollama lifecycle ──────────────────────────────────────────────────────────

def ollama_is_running() -> bool:
    try:
        req.get("http://localhost:11434/api/tags", timeout=2)
        return True
    except Exception:
        return False


def start_ollama():
    global OLLAMA_PROC
    if ollama_is_running():
        print("[server] Ollama already running.")
        return
    print("[server] Starting ollama serve...")
    OLLAMA_PROC = subprocess.Popen(
        ["ollama", "serve"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Wait up to 15s for ollama to become ready
    for _ in range(30):
        if ollama_is_running():
            print("[server] Ollama ready.")
            return
        time.sleep(0.5)
    print("[server] Warning: Ollama did not start in time.")


def stop_ollama():
    global OLLAMA_PROC
    if OLLAMA_PROC:
        print("[server] Stopping ollama (we started it)...")
        OLLAMA_PROC.terminate()
        OLLAMA_PROC = None
    # Also kill any other ollama processes
    subprocess.run(["pkill", "-f", "ollama serve"],  check=False)
    subprocess.run(["pkill", "-f", "ollama runner"], check=False)


# ── Startup / shutdown ────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    start_ollama()
    # Start the heartbeat watchdog in the background
    asyncio.create_task(heartbeat_watchdog())


@app.on_event("shutdown")
async def shutdown():
    stop_ollama()


# ── Heartbeat watchdog ────────────────────────────────────────────────────────

async def heartbeat_watchdog():
    """
    Runs forever in the background. If the browser stops sending heartbeats
    (tab closed, Chrome crashed, etc.) for more than HEARTBEAT_TIMEOUT seconds,
    shut down cleanly. This is the belt-and-suspenders safety net.
    """
    while True:
        await asyncio.sleep(15)
        if time.time() - LAST_HEARTBEAT > HEARTBEAT_TIMEOUT:
            print("[server] No heartbeat received — browser appears closed. Shutting down.")
            stop_ollama()
            os._exit(0)


# ── Request/response models ───────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
async def index():
    return FileResponse("static/index.html")


@app.get("/health")
async def health():
    return {"ollama": "running" if ollama_is_running() else "offline"}


@app.post("/heartbeat")
async def heartbeat():
    global LAST_HEARTBEAT
    LAST_HEARTBEAT = time.time()
    return {"ok": True}


@app.post("/shutdown")
async def shutdown_route():
    """Called by the browser's beforeunload beacon when the tab closes."""
    print("[server] Shutdown requested by browser.")
    stop_ollama()
    # Schedule exit after response is sent
    asyncio.create_task(_delayed_exit())
    return {"ok": True}


async def _delayed_exit():
    await asyncio.sleep(0.5)
    os._exit(0)


async def _auto_extract_memory(user_message: str, jarvis_reply: str):
    """
    Runs in the background after every chat response.
    Uses Gemma4 to decide if anything is worth saving to Obsidian.
    Never blocks the main response — fires and forgets.
    """
    try:
        from tools import llm_tool
        from agents import memory_agent

        EXTRACT_SYSTEM = """You are a memory filter for an AI assistant called Jarvis.
Read this conversation exchange and decide if there is anything worth remembering long-term.

Worth remembering:
- Personal facts (name, job, location, hardware, preferences)
- Project details (what they're building, tech stack, decisions)
- Explicit requests to remember something

NOT worth remembering:
- General questions and answers (what is X, how does Y work)
- One-off tasks (generate an image, search the web)
- Small talk

If there is something worth remembering, respond with EXACTLY:
REMEMBER: <the fact in one short sentence> | CATEGORY: <preference|facts|project:name>

If there is nothing worth remembering, respond with EXACTLY:
NOTHING"""

        prompt = f"User: {user_message}\nJarvis: {jarvis_reply}"
        result = await asyncio.to_thread(
            llm_tool.ask, prompt, EXTRACT_SYSTEM, llm_tool.FAST_MODEL, 0.1, 60
        )

        result = result.strip()
        if result.startswith("REMEMBER:"):
            # Parse: "REMEMBER: <fact> | CATEGORY: <cat>"
            parts    = result[len("REMEMBER:"):].split("| CATEGORY:")
            content  = parts[0].strip()
            category = parts[1].strip() if len(parts) > 1 else "facts"
            memory_agent.run({"task": "remember", "content": content, "category": category})
            print(f"[auto-memory] Saved: {content} ({category})")

    except Exception as e:
        print(f"[auto-memory] Error: {e}")


@app.post("/chat")
async def chat(req: ChatRequest):
    """
    Run brain immediately, return stream_id, then run agent in background.
    This way long-running agents (Blender, image gen) don't block the HTTP response.
    """
    message = req.message.strip()
    if not message:
        return JSONResponse({"error": "Empty message"}, status_code=400)

    # Brain is fast (~1s via Groq) — run it now before returning
    brain_response = await asyncio.to_thread(brain.ask, message)
    action = brain_response.get("action", "unknown")
    reply  = brain_response.get("reply", "")
    params = brain_response.get("params", {})

    # Create stream slot immediately — agent will fill it in the background
    stream_id = str(uuid.uuid4())
    STREAMS[stream_id] = None   # placeholder — stream endpoint will wait

    # Run the agent in the background — fills STREAMS[stream_id] when done
    asyncio.create_task(_run_agent_and_fill_stream(
        stream_id, message, brain_response, action, reply, params
    ))

    return {
        "stream_id": stream_id,
        "action": action,
        "agent": brain_response.get("agent", ""),
    }


@app.get("/stream/{stream_id}")
async def stream(stream_id: str):
    """SSE endpoint — waits for agent to finish, then streams reply word by word."""

    async def generator():
        # Wait up to 300s for the agent to fill the stream slot
        for _ in range(3000):
            if stream_id in STREAMS and STREAMS[stream_id] is not None:
                break
            await asyncio.sleep(0.1)
        else:
            yield f"event: error\ndata: {json.dumps({'msg': 'Timed out waiting for agent'})}\n\n"
            return

        data = STREAMS.pop(stream_id, None)
        if not data:
            yield f"event: error\ndata: {json.dumps({'msg': 'Stream not found'})}\n\n"
            return

        text = data["text"] or ""
        card = data["card"]

        # Stream word by word
        words = text.split(" ")
        for i, word in enumerate(words):
            chunk = word + (" " if i < len(words) - 1 else "")
            yield f"event: token\ndata: {json.dumps({'text': chunk})}\n\n"
            await asyncio.sleep(0.03)

        # Send the card
        yield f"event: card\ndata: {json.dumps(card)}\n\n"

        # Done
        yield f"event: done\ndata: {{}}\n\n"

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )


async def _run_agent_and_fill_stream(stream_id, message, brain_response, action, reply, params):
    """Run the agent in the background and fill the stream slot when done."""
    try:
        agent_result = await asyncio.to_thread(orchestrator.dispatch, brain_response)
    except Exception as e:
        agent_result = f"Agent error: {e}"

    # Track conversation for auto-memory
    _SKIP_MEMORY_ACTIONS = {"get_time", "clarify", "unknown", "remember", "recall"}
    if action not in _SKIP_MEMORY_ACTIONS:
        jarvis_reply = agent_result if isinstance(agent_result, str) else reply
        CONVERSATION_BUFFER.append({"role": "user",   "content": message})
        CONVERSATION_BUFFER.append({"role": "jarvis", "content": jarvis_reply})
        while len(CONVERSATION_BUFFER) > MAX_BUFFER * 2:
            CONVERSATION_BUFFER.pop(0)
        asyncio.create_task(_auto_extract_memory(message, jarvis_reply))

    # Build card and stream text
    card = _build_card(action, params, agent_result, reply)

    FACTUAL = {"get_time", "search_files", "run_command"}
    if action == "web_search":
        stream_text = agent_result.split("|||")[0].strip() if "|||" in agent_result else agent_result
    elif action in FACTUAL:
        stream_text = agent_result
    elif action == "generate_image" and isinstance(agent_result, str) and agent_result.startswith("IMAGE:"):
        stream_text = reply
    elif action in ("write_code", "edit_file") and isinstance(agent_result, str) and agent_result.startswith(("CODE_FILE:", "FILE_UPDATED:")):
        stream_text = reply
    elif action == "generate_diagram" and isinstance(agent_result, str) and agent_result.startswith("DIAGRAM:"):
        stream_text = reply
    else:
        stream_text = agent_result if isinstance(agent_result, str) else reply

    # Fill the stream slot — the SSE generator is waiting for this
    STREAMS[stream_id] = {"text": stream_text, "card": card, "action": action}


# ── Card builder ──────────────────────────────────────────────────────────────

def _build_card(action: str, params: dict, agent_result: str, reply: str) -> dict:
    """
    Build a structured card payload for the frontend to render specially.
    Each action type gets its own card type with relevant data.
    """
    if action == "get_time":
        return {"type": "time", "value": agent_result}

    if action in ("search_files",):
        lines = agent_result.split("\n")
        return {"type": "files", "lines": lines, "query": params.get("query", "")}

    if action == "web_search":
        # agent_result format: "answer|||source1\nsource2" or plain text
        if "|||" in agent_result:
            answer, sources = agent_result.split("|||", 1)
            result_for_card = f"Sources:\n{sources.strip()}"
        else:
            answer = agent_result
            result_for_card = agent_result
        return {"type": "search", "query": params.get("query", ""), "result": result_for_card, "answer": answer.strip()}

    if action == "open_in_browser":
        return {"type": "browser", "query": params.get("query", ""), "result": agent_result}

    if action == "generate_image":
        # agent_result is "IMAGE:/absolute/path/to/file.png" or an error string
        if agent_result.startswith("IMAGE:"):
            abs_path  = agent_result[6:]           # strip "IMAGE:" prefix
            filename  = abs_path.split("/")[-1]    # just the filename
            url       = f"/images/{filename}"
            return {"type": "image", "url": url, "description": params.get("description", "")}
        return {"type": "text", "text": agent_result}

    if action == "write_code":
        # agent_result is "CODE_FILE:/path/to/file.py" or an error string
        if agent_result.startswith("CODE_FILE:"):
            filepath = agent_result[len("CODE_FILE:"):]
            filename = filepath.split("/")[-1]
            code_content = ""
            try:
                code_content = Path(filepath).read_text(encoding="utf-8")
            except Exception:
                pass
            return {"type": "code_file", "filepath": filepath, "filename": filename,
                    "description": params.get("description", ""), "code": code_content}
        return {"type": "text", "text": agent_result}

    if action == "edit_file":
        # agent_result is "FILE_UPDATED:/path/to/file.py" or an error string
        if agent_result.startswith("FILE_UPDATED:"):
            filepath = agent_result[len("FILE_UPDATED:"):]
            filename = filepath.split("/")[-1]
            code_content = ""
            try:
                code_content = Path(filepath).read_text(encoding="utf-8")
            except Exception:
                pass
            return {"type": "code_file", "filepath": filepath, "filename": filename,
                    "description": params.get("instruction", "File updated"), "code": code_content}
        return {"type": "text", "text": agent_result}

    if action == "explain_code":
        return {"type": "text", "text": agent_result}

    if action == "generate_cad":
        return {"type": "3d_preview", "description": params.get("description", "")}

    if action in ("generate_blender", "generate_shape_e"):
        return {"type": "3d_blender", "description": params.get("description", ""), "result": agent_result}

    if action == "generate_diagram":
        if isinstance(agent_result, str) and agent_result.startswith("DIAGRAM:"):
            mermaid_code = agent_result[len("DIAGRAM:"):]
            return {"type": "diagram", "code": mermaid_code, "description": params.get("description", "")}
        return {"type": "text", "text": agent_result}

    if action == "clarify":
        return {"type": "clarify", "question": params.get("question", reply), "best_guess": params.get("best_guess", "")}

    if action == "unknown":
        return {"type": "unknown", "text": agent_result}

    return {"type": "text", "text": agent_result}
