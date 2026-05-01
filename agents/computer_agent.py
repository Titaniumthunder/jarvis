# computer_agent.py
# Controls the Mac: runs terminal commands and searches for files.
#
# Handles two tasks:
#   "run_command"  — runs a safe shell command and returns the output
#   "search_files" — searches for files matching a pattern under a directory

import subprocess
import pathlib


# Commands that could cause damage are blocked outright.
# This list grows over time as you think of more dangerous operations.
BLOCKED_COMMANDS = [
    "rm ", "rmdir", "sudo", "mkfs", "dd ",
    ":(){:|:&};:", "shutdown", "reboot", "halt",
    "chmod 777", "chown", "> /dev/", "curl", "wget",
]


def run(command: dict) -> str:
    """
    Dispatch to the right computer task based on command["task"].

    Args:
        command: dict with at least a "task" key, plus task-specific keys.

    Returns:
        A string result to show/speak to the user.
    """
    task = command.get("task", "")

    if task == "run_command":
        return _run_command(command.get("cmd", ""))

    if task == "search_files":
        return _search_files(
            query=command.get("query", ""),
            directory=command.get("directory", str(pathlib.Path.home()))
        )

    if task == "web_search":
        from tools import search_tool
        return search_tool.search_and_summarise(command.get("query", ""))

    if task == "open_in_browser":
        from tools import search_tool
        return search_tool.open_in_browser(
            query=command.get("query", ""),
            browser=command.get("browser", "chrome")
        )

    return f"Computer agent doesn't know how to handle task: '{task}'"


def _run_command(cmd: str) -> str:
    """
    Run a shell command and return its output (stdout + stderr).
    Blocks dangerous commands before they execute.
    """
    if not cmd:
        return "No command provided."

    # Safety check — refuse anything that looks dangerous
    cmd_lower = cmd.lower()
    for blocked in BLOCKED_COMMANDS:
        if blocked in cmd_lower:
            return f"Blocked: '{blocked}' is not allowed for safety reasons."

    print(f"[computer_agent] Running: {cmd}")
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=10    # never hang longer than 10 seconds
        )
        output = (result.stdout + result.stderr).strip()
        return output if output else "(command ran with no output)"
    except subprocess.TimeoutExpired:
        return "Command timed out after 10 seconds."
    except Exception as e:
        return f"Command failed: {e}"


def _search_files(query: str, directory: str) -> str:
    """
    Search for files under `directory`.
    - query="*" or query="" → list the top-level contents of the directory
    - query="*.py" or query="something" → search for matching files recursively
    """
    search_path = pathlib.Path(directory).expanduser()
    if not search_path.exists():
        search_path = pathlib.Path.home()

    # "What's in this folder?" — list top-level contents
    if not query or query.strip() in ("*", "all", "everything"):
        return _list_directory(search_path)

    print(f"[computer_agent] Searching for '{query}' in {search_path}")

    try:
        matches = list(search_path.rglob(f"*{query}*"))[:20]
    except PermissionError:
        return f"Permission denied searching in {search_path}"

    if not matches:
        return f"No files matching '{query}' found in {search_path}."

    lines = [f"Found {len(matches)} file(s) matching '{query}':"]
    for match in matches:
        lines.append(f"  {match}")
    return "\n".join(lines)


def _list_directory(path: pathlib.Path) -> str:
    """List the immediate contents of a directory, showing folders and files separately."""
    try:
        items = sorted(path.iterdir())
    except PermissionError:
        return f"Permission denied: {path}"
    except NotADirectoryError:
        return f"{path} is not a folder."

    if not items:
        return f"{path} is empty."

    folders = [i for i in items if i.is_dir() and not i.name.startswith('.')]
    files   = [i for i in items if i.is_file() and not i.name.startswith('.')]

    lines = [f"Contents of {path.name}/ ({len(folders)} folders, {len(files)} files):"]
    for f in folders:
        lines.append(f"  📁 {f.name}/")
    for f in files:
        lines.append(f"  📄 {f.name}")
    return "\n".join(lines)
