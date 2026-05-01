# code_agent.py
# Handles all coding tasks: writing new scripts, editing files, explaining code.
#
# Actions handled:
#   write_code   → generate code from a description and save to a file
#   edit_file    → read an existing file, apply an instruction, save back
#   explain_code → read a file and explain what it does in plain English

import pathlib
from tools import llm_tool, file_tool

# Where generated code files are saved
CODE_OUTPUT_DIR = (
    pathlib.Path.home()
    / "Personal Project"
    / "Desktop assistant"
    / "jarvis"
    / "code_output"
)

CODE_SYSTEM = """You are an expert software engineer.
Rules:
- When writing code: output ONLY the code — no explanations, no markdown fences, no triple backticks.
- When editing code: return the COMPLETE updated file, not just the changed section.
- When explaining code: be concise, clear, and use plain English. No jargon unless necessary.
- Always add brief comments to explain non-obvious parts.
- Write clean, readable code."""

# File extensions by language
EXTENSIONS = {
    "python":     ".py",
    "javascript": ".js",
    "typescript": ".ts",
    "bash":       ".sh",
    "shell":      ".sh",
    "html":       ".html",
    "css":        ".css",
    "json":       ".json",
    "text":       ".txt",
}


def run(command: dict) -> str:
    task = command.get("task", "")

    if task == "write_code":
        return _write_code(command)
    elif task == "edit_file":
        return _edit_file(command)
    elif task == "explain_code":
        return _explain_code(command)
    else:
        return f"[code_agent] Unknown task: '{task}'"


# ── write_code ────────────────────────────────────────────────────────────────

def _write_code(command: dict) -> str:
    description = command.get("description", "").strip()
    filename    = command.get("filename", "").strip()
    language    = command.get("language", "python").strip().lower()

    if not description:
        return "[code_agent] ERROR: No description provided for write_code."

    # Build a filename if none given
    if not filename:
        slug = description.lower().replace(" ", "_")[:30]
        ext  = EXTENSIONS.get(language, ".txt")
        filename = slug + ext
    elif "." not in filename:
        filename += EXTENSIONS.get(language, ".txt")

    CODE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    save_path = CODE_OUTPUT_DIR / filename

    print(f"[code_agent] Writing {language} code: '{description}'")
    prompt = (
        f"Write a {language} script that does the following:\n\n"
        f"{description}\n\n"
        f"Output ONLY the code. No explanations, no markdown, no backticks."
    )
    code = llm_tool.ask(prompt, system=CODE_SYSTEM, temperature=0.2, max_tokens=2000)
    code = _strip_fences(code)

    result = file_tool.write_file(str(save_path), code)
    print(f"[code_agent] {result}")
    return f"CODE_FILE:{save_path}"


# ── edit_file ─────────────────────────────────────────────────────────────────

def _edit_file(command: dict) -> str:
    filepath    = command.get("filepath", "").strip()
    instruction = command.get("instruction", "").strip()

    if not filepath:
        return "[code_agent] ERROR: No filepath provided for edit_file."
    if not instruction:
        return "[code_agent] ERROR: No instruction provided for edit_file."

    existing = file_tool.read_file(filepath)
    if existing.startswith("[file_tool] ERROR"):
        return existing

    print(f"[code_agent] Editing '{filepath}': {instruction}")
    prompt = (
        f"Here is the existing file at {filepath}:\n\n"
        f"{existing}\n\n"
        f"Instruction: {instruction}\n\n"
        f"Return the COMPLETE updated file. Output ONLY the code, no explanations, no backticks."
    )
    updated = llm_tool.ask(prompt, system=CODE_SYSTEM, temperature=0.2, max_tokens=3000)
    updated = _strip_fences(updated)

    result = file_tool.write_file(filepath, updated)
    print(f"[code_agent] {result}")
    return f"FILE_UPDATED:{filepath}"


# ── explain_code ──────────────────────────────────────────────────────────────

def _explain_code(command: dict) -> str:
    filepath = command.get("filepath", "").strip()

    if not filepath:
        return "[code_agent] ERROR: No filepath provided for explain_code."

    code = file_tool.read_file(filepath)
    if code.startswith("[file_tool] ERROR"):
        return code

    filename = pathlib.Path(filepath).name
    print(f"[code_agent] Explaining '{filename}'")
    prompt = (
        f"Here is the file '{filename}':\n\n"
        f"{code}\n\n"
        f"Explain what this code does in plain English. Be concise."
    )
    return llm_tool.ask(prompt, system=CODE_SYSTEM, temperature=0.3, max_tokens=800)


# ── helpers ───────────────────────────────────────────────────────────────────

def _strip_fences(code: str) -> str:
    """Remove markdown code fences if the model wrapped the output."""
    lines = code.strip().splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()
