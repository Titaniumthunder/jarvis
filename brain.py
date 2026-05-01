# brain.py
# The LLM "brain" for Jarvis — sends user commands to Gemini and gets back
# structured JSON telling the orchestrator what to do.
#
# How it works:
#   1. We send the user's message + a system prompt to Gemini 2.0 Flash
#   2. Gemini returns a JSON object like:
#      { "action": "get_time", "agent": "computer", "params": {} }
#   3. We validate the JSON against the known action library
#   4. Return the validated dict to the orchestrator
#
# Falls back to local Ollama (Gemma4) if Gemini is unavailable.

import json
import requests
from tools import groq_tool

# ── Action library ───────────────────────────────────────────────────────────
# Every action Jarvis can perform lives here.
# The brain can ONLY return actions from this list — anything else is rejected.
KNOWN_ACTIONS = {
    "get_time",          # return current time
    "search_files",      # search local files
    "web_search",        # search the web and return answer in terminal
    "open_in_browser",   # open a search or URL in Chrome
    "run_command",       # run a terminal command
    "move_arm",          # move the robot arm
    "generate_image",    # generate a 2D image with Stable Diffusion and show it
    "generate_cad",      # generate Three.js HTML preview in browser
    "generate_shape_e",  # generate organic 3D mesh with TripoSR AI → open in Blender
    "open_bambu",        # open a file in Bambu Studio
    "answer_question",   # answer from local knowledge
    "watch_printer",     # check the printer camera
    "write_code",        # write new code to a file
    "edit_file",         # edit an existing file
    "explain_code",      # explain what a file does
    "generate_blender_mcp",  # create object in live Blender via MCP socket (Gemma4)
    "refine_blender_mcp",    # refine/fix the last created Blender object (Gemma4)
    "generate_blender_cc",   # create object in Blender using Claude Code (better quality)
    "refine_blender_cc",     # refine last Blender object using Claude Code
    "remember",              # save something to memory
    "recall",                # retrieve something from memory
    "generate_diagram",      # generate a Mermaid.js diagram (flowchart, logic gate, etc.)
    "clarify",           # ask the user to clarify their command
    "unknown",           # fallback when nothing matches
}

# ── System prompt ────────────────────────────────────────────────────────────
# This tells Llama 3 exactly what role it plays and what format to return.
SYSTEM_PROMPT = """
You are Jarvis, a local AI desktop assistant running on a Mac.
You control a robot arm, manage files, run terminal commands,
generate 3D models, and monitor a 3D printer.

When the user speaks a command, you must respond with ONLY a JSON object.
No explanation, no markdown — just raw JSON.

The JSON must have these fields:
  "action"  — one of the actions listed below
  "agent"   — which specialist agent handles this (arm, computer, cad, knowledge, vision)
  "params"  — a dict of any extra info needed (can be empty {})
  "reply"   — a short spoken reply to say back to the user (1-2 sentences max)

Available actions:
  get_time       → agent: computer,   params: {}
  search_files   → agent: computer,   params: {"query": "...", "directory": "..."}
  web_search     → agent: computer,   params: {"query": "..."}
  open_in_browser→ agent: computer,   params: {"query": "...", "browser": "chrome"}
     - "what's in X folder" or "show X folder" → query: "*", directory: full path to that folder
     - "find X files" → query: "*.py" or filename pattern, directory: best guess or home
  run_command    → agent: computer,   params: {"cmd": "..."}
  move_arm       → agent: arm,        params: {"target_object": "...", "motion": "..."}
  generate_image   → agent: cad, params: {"description": "...", "filename": "..."}
  generate_cad     → agent: cad, params: {"description": "...", "filename": "..."}
  generate_shape_e → agent: cad, params: {"description": "...", "filename": "..."}
  open_bambu       → agent: cad, params: {"stl_path": "..."}
  answer_question→ agent: knowledge,  params: {"question": "..."}
  watch_printer  → agent: vision,     params: {}
  write_code          → agent: code,        params: {"description": "...", "filename": "...", "language": "python"}
  edit_file           → agent: code,        params: {"filepath": "...", "instruction": "..."}
  explain_code        → agent: code,        params: {"filepath": "..."}
  generate_blender_mcp → agent: blender_mcp, params: {"description": "..."}   (faster, less accurate)
  refine_blender_mcp   → agent: blender_mcp, params: {"instruction": "..."}
  generate_blender_cc  → agent: blender_cc,  params: {"description": "..."}   (Claude-powered, higher quality)
  refine_blender_cc    → agent: blender_cc,  params: {"instruction": "..."}
  remember             → agent: memory, params: {"content": "...", "category": "facts|preference|project:name|person:name"}
  recall               → agent: memory, params: {"query": "..."}
  generate_diagram     → agent: diagram, params: {"description": "..."}
  clarify        → agent: none,       params: {"question": "what you need to know"}
  unknown        → agent: none,       params: {}

IMPORTANT RULES for clarify vs unknown:
  - Use "clarify" when you understood the INTENT but need more info to act.
    Example: "open the file" → you need to know WHICH file
    Example: "move it" → you need to know WHAT to move and WHERE
    Example: "generate a model" → you need to know WHAT model
  - Use "unknown" only when the command makes no sense at all and a clarifying
    question wouldn't help.
  - NEVER use "unknown" when "clarify" would be more helpful.

  SMART CLARIFICATION RULES:
  - If the user says something that SOUNDS LIKE a known file, folder, app or object
    but isn't exact, make your BEST GUESS and ask for confirmation instead of asking
    what they meant from scratch.
  - Format: "Did you mean [your best guess]?" or "Is this what you meant: [best guess]?"
  - Examples:
    "open flappy bot" → best guess is "flappy-bot" folder/app → ask "Did you mean flappy-bot?"
    "open personal project" → best guess is "Personal Project" folder → ask "Did you mean the Personal Project folder?"
    "find my jarvis files" → best guess is the jarvis project folder → ask "Did you mean the jarvis project folder?"
  - Put your best guess in the "best_guess" param so the system can use it directly if confirmed.

Example — user says "What time is it?":
{"action": "get_time", "agent": "computer", "params": {}, "reply": "Checking the time for you now."}

Example — user says "search for the best Python frameworks":
{"action": "web_search", "agent": "computer", "params": {"query": "best Python frameworks"}, "reply": "Searching the web for that now."}

Example — user says "open latest iPhone reviews in browser" or "open in Chrome":
{"action": "open_in_browser", "agent": "computer", "params": {"query": "latest iPhone reviews", "browser": "chrome"}, "reply": "Opening that in Chrome now."}

Example — user says "What's in my Personal Project folder?":
{"action": "search_files", "agent": "computer", "params": {"query": "*", "directory": "~/Personal Project"}, "reply": "Looking inside your Personal Project folder."}

Example — user says "Pick up the red block":
{"action": "move_arm", "agent": "arm", "params": {"target_object": "red block", "motion": "pick_up"}, "reply": "On it, reaching for the red block."}

Example — user says "Generate an image of a dragon" or "Draw me a sunset":
{"action": "generate_image", "agent": "cad", "params": {"description": "a dragon", "filename": "dragon"}, "reply": "Generating that image now, give me a moment."}

Example — user says "Design a curved vase":
{"action": "generate_cad", "agent": "cad", "params": {"description": "curved vase", "filename": "vase"}, "reply": "Generating a 3D preview now."}

Example — user says "Generate Pikachu holding a flower pot" or anything organic/character-like:
{"action": "generate_shape_e", "agent": "cad", "params": {"description": "Pikachu holding a flower pot", "filename": "pikachu"}, "reply": "Generating that with TripoSR AI now — give me about 30 seconds."}

Example — user says "what can you do?" or "what are your capabilities?" or "what tasks can you perform?":
{"action": "answer_question", "agent": "knowledge", "params": {"question": "what can Jarvis do"}, "reply": "Here's what I can help you with."}

Example — user says "open the file" (no clue what file):
{"action": "clarify", "agent": "none", "params": {"question": "Which file would you like me to open?", "best_guess": ""}, "reply": "Which file would you like me to open?"}

Example — user says "open flappy bot" (sounds like a folder name):
{"action": "clarify", "agent": "none", "params": {"question": "Did you mean flappy-bot?", "best_guess": "flappy-bot"}, "reply": "Did you mean flappy-bot?"}

Example — user says "generate a model" (no description given):
{"action": "clarify", "agent": "none", "params": {"question": "What would you like me to generate? For example, a vase, a character, or something else?", "best_guess": ""}, "reply": "What would you like me to generate?"}

Example — user says "write me a python script that renames all files in a folder":
{"action": "write_code", "agent": "code", "params": {"description": "rename all files in a folder", "filename": "rename_files.py", "language": "python"}, "reply": "Writing that script for you now."}

Example — user says "write a bash script that backs up my desktop":
{"action": "write_code", "agent": "code", "params": {"description": "back up the desktop folder to a zip file", "filename": "backup_desktop.sh", "language": "bash"}, "reply": "Writing that backup script now."}

Example — user says "edit /path/to/file.py to add error handling":
{"action": "edit_file", "agent": "code", "params": {"filepath": "/path/to/file.py", "instruction": "add error handling"}, "reply": "Editing that file for you now."}

Example — user says "explain what brain.py does" or "what does this file do":
{"action": "explain_code", "agent": "code", "params": {"filepath": "./brain.py"}, "reply": "Let me read through that file and explain it."}

Example — user says "remember that my printer is a Bambu X1C":
{"action": "remember", "agent": "memory", "params": {"content": "printer is a Bambu X1C", "category": "preference"}, "reply": "Got it, I'll remember that."}

Example — user says "remember I prefer dark mode" or "save that I use Python":
{"action": "remember", "agent": "memory", "params": {"content": "prefers dark mode", "category": "preference"}, "reply": "Remembered."}

Example — user says "what do you know about my printer?" or "do you remember my setup?":
{"action": "recall", "agent": "memory", "params": {"query": "printer"}, "reply": "Let me check my memory."}

Example — user says "draw me a flowchart for user login" or "diagram the logic gates for a half adder" or "show me a sequence diagram for authentication":
{"action": "generate_diagram", "agent": "diagram", "params": {"description": "user login flowchart"}, "reply": "Drawing that diagram for you now."}

Example — user says "create a gear in Blender" or "build something in Blender" (default to CC for quality):
{"action": "generate_blender_cc", "agent": "blender_cc", "params": {"description": "a mechanical gear with 12 teeth"}, "reply": "On it — using Claude to build that in Blender."}

Example — user says "make it better quality" or "use Claude for blender" or "create a detailed X in blender":
{"action": "generate_blender_cc", "agent": "blender_cc", "params": {"description": "a detailed coffee mug with a handle"}, "reply": "Using Claude to generate that in Blender now."}

Example — user says "use the faster version" or "quick blender" or "quick 3d":
{"action": "generate_blender_mcp", "agent": "blender_mcp", "params": {"description": "a simple cube"}, "reply": "Building that in Blender now."}

Example — user says "make the teeth wider" or "refine it" or "fix it" or "add a hole" or "that looks wrong":
{"action": "refine_blender_cc", "agent": "blender_cc", "params": {"instruction": "make the teeth wider"}, "reply": "Updating the object in Blender now."}
""".strip()


def ask(user_message: str) -> dict:
    """
    Send a message to Gemini and return the validated JSON response as a dict.
    Falls back to Ollama if Gemini is unavailable.

    Args:
        user_message: The transcribed (or typed) command from the user.

    Returns:
        A dict with keys: action, agent, params, reply
        On any error, returns a safe fallback dict.
    """
    prompt = f"{SYSTEM_PROMPT}\n\nUser: {user_message}\nJarvis:"

    try:
        raw_text = groq_tool.ask_json(prompt, temperature=0.1)
        result = _parse_and_validate(raw_text, user_message)
        print(f"[brain] ✓ Action: {result.get('action')} | Agent: {result.get('agent')} | via Groq")
        return result
    except Exception as e:
        print(f"[brain] Groq error: {e} — falling back to Ollama")

    # Ollama fallback
    OLLAMA_URL = "http://localhost:11434/api/generate"
    MODEL_NAME = "gemma4:latest"
    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.2, "num_predict": 300}
    }
    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=120)
        response.raise_for_status()
        raw_text = response.json().get("response", "")
        return _parse_and_validate(raw_text, user_message)
    except requests.exceptions.ConnectionError:
        print("[brain] ERROR: Ollama also not running.")
        return _fallback("Neither Gemini nor Ollama is available.")
    except Exception as e:
        print(f"[brain] Ollama fallback error: {e}")
        return _fallback(str(e))


def _parse_and_validate(raw_text: str, original_message: str) -> dict:
    """
    Parse the raw string from Ollama into a dict, then validate it.

    Ollama sometimes wraps JSON in markdown fences — we strip those first.
    Then we check that the action is in our known action library.
    """
    # Strip markdown code fences if present (```json ... ```)
    text = raw_text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        print(f"[brain] JSON parse error: {e}")
        print(f"[brain] Raw response was: {raw_text[:200]}")
        return _fallback("I couldn't understand that response format.")

    # Validate required fields exist.
    # "action", "agent", "params" are hard requirements — without them we can't act.
    # "reply" is optional — smaller models sometimes skip it, so we fill in a default.
    for field in ("action", "agent", "params"):
        if field not in data:
            print(f"[brain] Missing field '{field}' in response: {data}")
            return _fallback("Response was missing required fields.")

    # Fill in a default reply if the model forgot to include one
    if "reply" not in data:
        data["reply"] = "On it."

    # Validate the action is in our known list
    action = data["action"]
    if action not in KNOWN_ACTIONS:
        print(f"[brain] Unknown action '{action}' — rejecting.")
        return _fallback(f"I don't know how to '{action}' yet.")

    # All good — return the validated response
    print(f"[brain] ✓ Action: {action} | Agent: {data['agent']}")
    return data


def _fallback(reason: str) -> dict:
    """Return a safe do-nothing response when something goes wrong."""
    return {
        "action": "unknown",
        "agent": "none",
        "params": {},
        "reply": f"Sorry, I ran into a problem: {reason}"
    }
