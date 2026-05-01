# blender_mcp_tool.py
# Connects to the Blender MCP socket server (port 9876) and sends Python
# commands to a live Blender session with real-time feedback.
#
# Auto-launch: if Blender isn't open, this tool opens it automatically
# with a startup script that calls bpy.ops.blendermcp.start_server()
# so the MCP socket is ready without any manual steps.

import socket
import json
import time
import subprocess
import pathlib

from tools import paths

HOST    = "localhost"
PORT    = 9876
TIMEOUT = 30  # seconds per command

BLENDER_PATH = paths.BLENDER_PATH

# Startup script written to a temp file and passed to Blender via --python
_STARTUP_SCRIPT = paths.BLENDER_SCRIPTS / "_mcp_autoconnect.py"


def _send(code: str) -> dict:
    """
    Send a single Python command to Blender and return the response dict.
    Protocol: plain JSON over TCP — send JSON, read until complete response.
    """
    payload = json.dumps({"type": "execute_code", "params": {"code": code}})

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(TIMEOUT)
            s.connect((HOST, PORT))
            s.sendall(payload.encode("utf-8"))

            buffer = b""
            while True:
                chunk = s.recv(8192)
                if not chunk:
                    break
                buffer += chunk
                try:
                    return json.loads(buffer.decode("utf-8"))
                except json.JSONDecodeError:
                    continue

            return {"status": "error", "message": "Connection closed before full response"}

    except ConnectionRefusedError:
        return {"status": "error", "message": "not_connected"}
    except socket.timeout:
        return {"status": "error", "message": "Blender MCP timed out."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def _write_autoconnect_script():
    """Write a Blender startup script that auto-connects the MCP addon."""
    _STARTUP_SCRIPT.parent.mkdir(parents=True, exist_ok=True)
    _STARTUP_SCRIPT.write_text("""
import bpy

def _autoconnect():
    try:
        # Set port to 9876 (default)
        bpy.context.scene.blendermcp_port = 9876
        bpy.ops.blendermcp.start_server()
        print("[jarvis] BlenderMCP auto-connected on port 9876")
    except Exception as e:
        print(f"[jarvis] BlenderMCP auto-connect failed: {e}")
    return None  # run once, don't repeat

bpy.app.timers.register(_autoconnect, first_interval=1.5)
""".strip())


def launch_blender() -> bool:
    """
    Open Blender with the MCP auto-connect script.
    Waits up to 15 seconds for the socket to become available.
    Returns True if connected, False if timed out.
    """
    if not pathlib.Path(BLENDER_PATH).exists():
        print(f"[blender_mcp] Blender not found at {BLENDER_PATH}")
        return False

    print("[blender_mcp] Opening Blender and auto-connecting MCP...")
    _write_autoconnect_script()

    subprocess.Popen([BLENDER_PATH, "--python", str(_STARTUP_SCRIPT)])

    # Poll until the socket is available (max 15 seconds)
    for i in range(15):
        time.sleep(1)
        if is_connected():
            print("[blender_mcp] Blender MCP connected.")
            return True
        print(f"[blender_mcp] Waiting for Blender... ({i + 1}s)")

    print("[blender_mcp] Timed out waiting for Blender MCP.")
    return False


def ensure_connected() -> bool:
    """
    Check if MCP is connected. If not, launch Blender automatically.
    Returns True if connected (or successfully launched), False otherwise.
    """
    if is_connected():
        return True
    return launch_blender()


def run_code(code: str) -> str:
    """Execute Python code in Blender. Returns result or error string."""
    resp = _send(code)
    if resp.get("status") == "success":
        return resp.get("result", "(done)")
    return f"[blender_mcp] ERROR: {resp.get('message', resp)}"


def is_connected() -> bool:
    """Check if Blender MCP is running and reachable."""
    resp = _send("print('ping')")
    return resp.get("status") == "success"


def clear_scene() -> str:
    """Delete everything in the scene except camera and light."""
    return run_code("""
import bpy
bpy.ops.object.select_all(action='SELECT')
for obj in bpy.context.selected_objects:
    if obj.type in ('CAMERA', 'LIGHT'):
        obj.select_set(False)
bpy.ops.object.delete()
print("Scene cleared")
""")


def get_scene_info() -> str:
    """Return a summary of what's currently in the scene."""
    return run_code("""
import bpy
objects = [(obj.name, obj.type) for obj in bpy.context.scene.objects]
print(objects)
""")
