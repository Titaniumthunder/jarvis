"""arm_sim_client.py — Talks to the MuJoCo Franka Panda server on TCP 9877.

The server lives in a separate venv (`~/mujoco-venv`, Python 3.10) because
MuJoCo wheels don't ship for Python 3.14. This client runs in the main Jarvis
venv and only depends on the standard library.

Same auto-launch pattern as `blender_mcp_tool.launch_blender()`:
- If the socket is dead, `ensure_running()` spawns the server via mjpython.
- We poll the socket until it answers `ping`, then return.
"""

import json
import os
import pathlib
import socket
import subprocess
import time

from tools import paths

HOST = "127.0.0.1"
PORT = 9877
TIMEOUT = 30.0  # seconds per command

MUJOCO_VENV = pathlib.Path.home() / "mujoco-venv"
MJPYTHON = MUJOCO_VENV / "bin" / "mjpython"
SERVER_SCRIPT = paths.JARVIS_ROOT / "tools" / "arm_sim_server.py"

LAUNCH_TIMEOUT = 25  # seconds to wait for the viewer to come up


# ─── Low-level transport ──────────────────────────────────────────────────────

def _send(payload: dict, timeout: float = TIMEOUT) -> dict:
    data = (json.dumps(payload) + "\n").encode("utf-8")
    try:
        with socket.create_connection((HOST, PORT), timeout=timeout) as s:
            s.sendall(data)
            buf = b""
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    break
                buf += chunk
                if b"\n" in buf:
                    break
            line = buf.split(b"\n", 1)[0]
            if not line:
                return {"status": "error", "message": "empty response"}
            return json.loads(line.decode("utf-8"))
    except ConnectionRefusedError:
        return {"status": "error", "message": "not_connected"}
    except socket.timeout:
        return {"status": "error", "message": "timed out"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ─── Public API ───────────────────────────────────────────────────────────────

def is_running() -> bool:
    return _send({"cmd": "ping"}, timeout=2.0).get("status") == "success"


def ensure_running() -> bool:
    """If the server isn't responding, spawn it via mjpython and wait."""
    if is_running():
        return True

    if not MJPYTHON.exists():
        print(f"[arm_sim_client] mjpython not found at {MJPYTHON}.")
        print("[arm_sim_client] Create ~/mujoco-venv with Python 3.10 and `pip install mujoco`.")
        return False

    if not SERVER_SCRIPT.exists():
        print(f"[arm_sim_client] Server script missing at {SERVER_SCRIPT}.")
        return False

    print("[arm_sim_client] Launching MuJoCo arm simulator (mjpython, passive viewer)...")
    # Detach from the parent process group so the server outlives this Python run.
    subprocess.Popen(
        [str(MJPYTHON), str(SERVER_SCRIPT)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    for i in range(LAUNCH_TIMEOUT):
        time.sleep(1)
        if is_running():
            print(f"[arm_sim_client] Connected after {i + 1}s.")
            return True
        print(f"[arm_sim_client] Waiting for arm sim... ({i + 1}s)")

    print("[arm_sim_client] Timed out waiting for arm sim to come up.")
    return False


def home() -> dict:
    return _send({"cmd": "home"})


def open_gripper() -> dict:
    return _send({"cmd": "open_gripper"})


def close_gripper() -> dict:
    return _send({"cmd": "close_gripper"})


def move_to(xyz) -> dict:
    return _send({"cmd": "move_to", "xyz": list(xyz)})
