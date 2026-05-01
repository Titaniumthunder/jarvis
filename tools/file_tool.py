# file_tool.py
# Read, write, and list files on the local filesystem.
#
# Safety rules:
#   - All paths must be inside the user's home directory
#   - Parent directories are created automatically on write
#   - System files (outside ~) are never touched

import pathlib

HOME = pathlib.Path.home()


def _safe_path(path: str) -> pathlib.Path:
    """Resolve and validate a path is within the home directory."""
    p = pathlib.Path(path).expanduser().resolve()
    if not str(p).startswith(str(HOME)):
        raise ValueError(f"Path '{path}' is outside home directory — not allowed.")
    return p


def read_file(path: str) -> str:
    """Read the contents of a file and return as a string."""
    try:
        p = _safe_path(path)
        return p.read_text(encoding="utf-8")
    except Exception as e:
        return f"[file_tool] ERROR reading {path}: {e}"


def write_file(path: str, content: str) -> str:
    """Write content to a file, creating parent directories if needed."""
    try:
        p = _safe_path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"[file_tool] Saved to {p}"
    except Exception as e:
        return f"[file_tool] ERROR writing {path}: {e}"


def list_dir(path: str) -> str:
    """List the contents of a directory."""
    try:
        p = _safe_path(path)
        if not p.is_dir():
            return f"[file_tool] ERROR: '{path}' is not a directory."
        items = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
        lines = []
        for item in items:
            icon = "📄" if item.is_file() else "📁"
            lines.append(f"{icon} {item.name}")
        return "\n".join(lines) if lines else "(empty directory)"
    except Exception as e:
        return f"[file_tool] ERROR listing {path}: {e}"


def file_exists(path: str) -> bool:
    """Check if a file exists."""
    try:
        return _safe_path(path).exists()
    except Exception:
        return False
