# blender_claude_agent.py
# Uses Claude Code CLI as a sub-agent to write high-quality Blender Python scripts,
# then sends them to Blender via the MCP socket.
#
# Why Claude instead of Gemma4?
#   Claude is far better at writing correct bpy/bmesh code, handling edge cases,
#   and producing clean geometry without hallucinating non-existent operators.

import subprocess
import json
import pathlib
import datetime
import re
from tools import blender_mcp_tool, groq_tool, paths

CLAUDE_BIN = paths.CLAUDE_CLI
SESSION_FILE = paths.JARVIS_ROOT / "_last_blender_session.json"
MAX_RETRIES = 3

BLENDER_SYSTEM_PROMPT = """You are an expert Blender Python (bpy) programmer.
Write a SINGLE self-contained Python script that creates the described 3D object in Blender.

MANDATORY FIRST LINES — always include these exactly:
    import bpy, bmesh
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)

Rules:
- Use bpy and bmesh only. No external imports.
- Use bmesh for custom geometry (extrusions, loops, bevels).
- Use bpy.ops.mesh.primitive_* for standard shapes (cylinders, spheres, cubes, tori).
- NEVER use these (they do NOT exist in Blender):
    bmesh.ops.polyextrude_face_region
    bmesh.ops.vert_add
    bmesh.ops.create_face_from_verts
    bpy.ops.object.location_set
- For extrusion: bmesh.ops.extrude_face_region() then bmesh.ops.translate()
- For smooth organic shapes: subdivisions + bpy.ops.object.shade_smooth()
- For mechanical/hard-surface: bpy.ops.object.shade_flat()
- Always end by selecting the created object and making it active.
- Add a simple diffuse material with an appropriate colour.
- Output ONLY the Python code. No markdown fences, no explanations, no comments."""


def run(params: dict) -> str:
    """Generate a 3D object in Blender using Claude as the code writer."""
    description = params.get("description", "a simple object")

    print(f"[blender_claude] Generating: '{description}'")

    # Ensure Blender MCP is connected
    connected = blender_mcp_tool.ensure_connected()
    if not connected:
        return "Could not connect to Blender. Make sure Blender is open with the MCP addon running."

    code = _generate_code(description)
    if not code:
        return "Claude failed to generate Blender code."

    result = _send_with_retry(description, code)
    return result


def refine(params: dict) -> str:
    """Refine the last Blender object based on a follow-up instruction."""
    instruction = params.get("instruction", "")
    session = _load_session()

    if not session:
        return "No previous Blender session found. Generate something first."

    prev_desc = session.get("description", "")
    prev_code = session.get("code", "")

    print(f"[blender_claude] Refining '{prev_desc}': {instruction}")

    connected = blender_mcp_tool.ensure_connected()
    if not connected:
        return "Could not connect to Blender. Make sure Blender is open with the MCP addon running."

    prompt = (
        f"Original description: {prev_desc}\n\n"
        f"Existing Blender Python script:\n{prev_code}\n\n"
        f"User wants to change: {instruction}\n\n"
        f"Rewrite the COMPLETE script with this change applied. Output ONLY Python code."
    )

    code = _ask_claude(prompt)
    if not code:
        return "Claude failed to generate refined code."

    return _send_with_retry(f"{prev_desc} (refined: {instruction})", code)


# ── Claude code generation ────────────────────────────────────────────────────

def _generate_code(description: str) -> str:
    # Pass system prompt + task as a combined prompt for Claude CLI
    # (_ask_groq also uses this same string but as the user turn only)
    prompt = (
        f"{BLENDER_SYSTEM_PROMPT}\n\n"
        f"Create this in Blender: {description}"
    )
    return _ask_claude(prompt)


def _ask_claude(prompt: str) -> str:
    """
    Call Claude CLI with -p flag and return the output.
    Falls back to Groq (Llama 3.3 70B) if Claude times out or fails.
    """
    print(f"[blender_claude] Asking Claude CLI to write code (~30-60s)...")
    try:
        result = subprocess.run(
            [CLAUDE_BIN, "--dangerously-skip-permissions", "-p", prompt],
            capture_output=True,
            text=True,
            timeout=90,
            stdin=subprocess.DEVNULL,   # prevent stdin hang
        )
        output = result.stdout.strip()
        print(f"[blender_claude] Claude CLI returned {len(output)} chars (exit {result.returncode})")
        if output:
            return _strip_fences(output)
        if result.stderr:
            print(f"[blender_claude] stderr: {result.stderr[:400]}")

    except subprocess.TimeoutExpired:
        print("[blender_claude] Claude CLI timed out — falling back to Groq")
    except FileNotFoundError:
        print(f"[blender_claude] Claude CLI not found at {CLAUDE_BIN} — falling back to Groq")
    except Exception as e:
        print(f"[blender_claude] Claude CLI failed: {e} — falling back to Groq")

    return _ask_groq(prompt)


def _ask_groq(prompt: str) -> str:
    """Fallback: use Groq (Llama 3.3 70B) to write the Blender code."""
    print(f"[blender_claude] Asking Groq to write Blender code...")
    try:
        raw = groq_tool.ask(prompt, temperature=0.2, max_tokens=1500)
        code = _strip_fences(raw)
        print(f"[blender_claude] Groq returned {len(code)} chars of code")
        return code
    except Exception as e:
        print(f"[blender_claude] Groq also failed: {e}")
        return ""


# ── Send + auto-retry ─────────────────────────────────────────────────────────

def _send_with_retry(description: str, code: str) -> str:
    last_error = ""
    current_code = code

    for attempt in range(1, MAX_RETRIES + 1):
        print(f"[blender_claude] Attempt {attempt}/{MAX_RETRIES}")
        try:
            result = blender_mcp_tool.run_code(current_code)
            if isinstance(result, dict):
                if result.get("status") == "success":
                    _save_session(description, current_code)
                    return f"Done! '{description}' is now in Blender."
                last_error = result.get("error", str(result))
            else:
                _save_session(description, current_code)
                return f"Done! '{description}' is now in Blender."
        except Exception as e:
            last_error = str(e)

        if attempt < MAX_RETRIES:
            print(f"[blender_claude] Error on attempt {attempt}: {last_error[:200]}")
            fix_prompt = (
                f"This Blender Python script failed with error:\n{last_error}\n\n"
                f"Original script:\n{current_code}\n\n"
                f"Fix the error. Output ONLY the corrected Python code."
            )
            fixed = _ask_claude(fix_prompt)
            if fixed:
                current_code = fixed

    return f"Blender generation failed after {MAX_RETRIES} attempts. Last error: {last_error[:200]}"


# ── Session persistence ───────────────────────────────────────────────────────

def _save_session(description: str, code: str):
    data = {
        "description": description,
        "code": code,
        "timestamp": datetime.datetime.now().isoformat(),
    }
    SESSION_FILE.write_text(json.dumps(data, indent=2))


def _load_session() -> dict:
    if SESSION_FILE.exists():
        try:
            return json.loads(SESSION_FILE.read_text())
        except Exception:
            pass
    return {}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _strip_fences(code: str) -> str:
    """Remove markdown code fences if present."""
    lines = code.strip().splitlines()
    if lines and re.match(r"^```", lines[0]):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()
