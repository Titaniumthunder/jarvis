# terminal_tool.py
# Run shell commands safely and return their output.
#
# Safety rules:
#   - Destructive commands (rm -rf, mkfs, dd, etc.) are blocked outright
#   - Commands time out after 30 seconds by default
#   - stdout and stderr are both captured and returned

import subprocess

# Commands that are never allowed, no matter what
BLOCKED = [
    "rm -rf",
    "rm -r /",
    "sudo rm",
    "mkfs",
    "dd if=",
    "chmod -R 777 /",
    ":(){ :|:& };:",   # fork bomb
    "> /dev/",
    "curl | sh",
    "wget | sh",
    "curl | bash",
    "wget | bash",
]


def run(cmd: str, timeout: int = 30) -> str:
    """
    Run a shell command and return its output as a string.

    Args:
        cmd:     The shell command to run.
        timeout: Max seconds to wait before killing the process.

    Returns:
        stdout output, or an error/blocked message string.
    """
    cmd_stripped = cmd.strip()
    cmd_lower    = cmd_stripped.lower()

    # Check for blocked commands
    for blocked in BLOCKED:
        if blocked.lower() in cmd_lower:
            return f"[terminal] BLOCKED: '{cmd_stripped}' contains a destructive pattern and cannot be run."

    try:
        result = subprocess.run(
            cmd_stripped,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        if result.returncode != 0:
            err = stderr or stdout or "(no output)"
            return f"[terminal] Command failed (exit {result.returncode}):\n{err}"

        return stdout or "(command ran, no output)"

    except subprocess.TimeoutExpired:
        return f"[terminal] ERROR: Command timed out after {timeout}s. It may still be running."
    except Exception as e:
        return f"[terminal] ERROR: {e}"
