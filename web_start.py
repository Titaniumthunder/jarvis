# web_start.py
# Single launcher for the Jarvis web UI.
#
# Usage: .venv/bin/python web_start.py
# Or:    ./jarvis-web
#
# What it does:
#   1. Checks port 7777 is free
#   2. Starts uvicorn (FastAPI server) — which auto-starts ollama
#   3. Opens http://localhost:7777 in your browser
#   4. When you Ctrl+C (or the server exits for any reason), kills ollama

import subprocess
import sys
import time
import os
import signal
import socket

PORT = 7777
JARVIS_DIR = os.path.dirname(os.path.abspath(__file__))


def port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("localhost", port)) != 0


def wait_for_server(port: int, timeout: float = 10.0) -> bool:
    """Poll until the server is accepting connections."""
    start = time.time()
    while time.time() - start < timeout:
        if not port_is_free(port):
            return True
        time.sleep(0.3)
    return False


def main():
    # ── Preflight checks ─────────────────────────────────────────────────────
    if not port_is_free(PORT):
        print(f"[jarvis-web] Port {PORT} is already in use.")
        print(f"[jarvis-web] Jarvis may already be running — open http://localhost:{PORT}")
        subprocess.Popen(["open", f"http://localhost:{PORT}"])
        sys.exit(0)

    # Find the venv python
    venv_python = os.path.join(JARVIS_DIR, ".venv", "bin", "python3")
    if not os.path.exists(venv_python):
        venv_python = os.path.join(JARVIS_DIR, ".venv", "bin", "python")

    print(f"[jarvis-web] Starting Jarvis web UI on http://localhost:{PORT}")
    print(f"[jarvis-web] Press Ctrl+C to stop everything.\n")

    # ── Start uvicorn ─────────────────────────────────────────────────────────
    # --reload makes uvicorn auto-restart when source .py files change (dev-friendly).
    # --reload-exclude prevents Blender output scripts and generated files from
    # triggering false restarts (blender_scripts/*.py are outputs, not source code).
    server_proc = subprocess.Popen(
        [venv_python, "-m", "uvicorn", "server:app",
         "--host", "0.0.0.0",
         "--port", str(PORT),
         "--log-level", "warning",
         "--reload",
         "--timeout-keep-alive", "300",
         "--reload-exclude", "blender_scripts/*",
         "--reload-exclude", "image_gen_output/*",
         "--reload-exclude", "shape_e_output/*",
         "--reload-exclude", "previews/*",
         "--reload-exclude", "static/*"],
        cwd=JARVIS_DIR,
    )

    # ── Wait for server to be ready ───────────────────────────────────────────
    if not wait_for_server(PORT):
        print("[jarvis-web] Server failed to start in time.")
        server_proc.terminate()
        sys.exit(1)

    # ── Open browser ─────────────────────────────────────────────────────────
    time.sleep(0.5)
    subprocess.Popen(["open", f"http://localhost:{PORT}"])
    print(f"[jarvis-web] Browser opened. Jarvis is running.")

    # ── Wait — block until server exits ──────────────────────────────────────
    try:
        server_proc.wait()
    except KeyboardInterrupt:
        print("\n[jarvis-web] Stopping Jarvis...")
    finally:
        # Kill the server and any orphaned ollama processes
        try:
            server_proc.terminate()
            server_proc.wait(timeout=3)
        except Exception:
            server_proc.kill()

        subprocess.run(["pkill", "-f", "ollama serve"],  check=False)
        subprocess.run(["pkill", "-f", "ollama runner"], check=False)
        print("[jarvis-web] Shut down complete.")


if __name__ == "__main__":
    main()
