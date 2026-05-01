# memory_agent.py
# Reads and writes to the Obsidian vault so Jarvis can remember things
# across conversations.
#
# Vault structure:
#   ~/Documents/Jarvis Memory/
#     preferences.md       — user preferences and hardware info
#     facts.md             — general facts the user has told Jarvis
#     projects/<name>.md   — per-project notes
#     people/<name>.md     — notes about people
#     conversations/       — daily conversation summaries (auto-written)

import pathlib
import datetime
from tools import llm_tool

VAULT = pathlib.Path.home() / "Documents" / "Jarvis Memory"

SUMMARISE_SYSTEM = """You are a memory assistant for an AI called Jarvis.
Your job is to extract key facts worth remembering from a conversation and
write them as concise bullet points in markdown.
Only include facts that would be useful to know in future conversations.
Do not include small talk or one-off questions."""

RECALL_SYSTEM = """You are Jarvis. Answer the user's question naturally and concisely based on the memories provided.
- Give a direct 1-2 sentence answer using the facts.
- Do NOT show raw markdown, dashes, timestamps, or file names.
- Do NOT say "based on my memories" — just answer directly."""


# ── Public API ────────────────────────────────────────────────────────────────

def run(command: dict) -> str:
    task = command.get("task", "")

    if task == "remember":
        return _remember(command.get("content", ""), command.get("category", "facts"))
    elif task == "recall":
        return _recall(command.get("query", ""))
    elif task == "summarise_conversation":
        return _summarise_conversation(command.get("messages", []))
    else:
        return f"[memory] Unknown task: {task}"


# ── Remember ──────────────────────────────────────────────────────────────────

def _remember(content: str, category: str = "facts") -> str:
    """Save a piece of information to the vault."""
    if not content:
        return "[memory] Nothing to remember."

    VAULT.mkdir(parents=True, exist_ok=True)

    # Choose the right file based on category
    if category == "preference":
        target = VAULT / "preferences.md"
    elif category.startswith("project:"):
        project = category[8:].strip().replace(" ", "_").lower()
        target = VAULT / "projects" / f"{project}.md"
        target.parent.mkdir(exist_ok=True)
    elif category.startswith("person:"):
        person = category[7:].strip().replace(" ", "_").lower()
        target = VAULT / "people" / f"{person}.md"
        target.parent.mkdir(exist_ok=True)
    else:
        target = VAULT / "facts.md"

    # Append as a timestamped bullet point
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d")
    entry = f"- [{timestamp}] {content}\n"

    # Create file with header if it doesn't exist
    if not target.exists():
        header = f"# {target.stem.replace('_', ' ').title()}\n\n"
        target.write_text(header)

    with open(target, "a") as f:
        f.write(entry)

    print(f"[memory] Saved to {target.name}: {content}")
    return f"Got it, I'll remember that."


# ── Recall ────────────────────────────────────────────────────────────────────

def _recall(query: str) -> str:
    """Search the vault for relevant memories."""
    if not VAULT.exists():
        return "I don't have any memories saved yet."

    query_lower = query.lower()
    matches = []

    # Search all markdown files in the vault
    for md_file in VAULT.rglob("*.md"):
        try:
            text = md_file.read_text(encoding="utf-8")
            lines = text.splitlines()
            for line in lines:
                if any(word in line.lower() for word in query_lower.split()):
                    matches.append(f"**{md_file.stem}**: {line.strip()}")
        except Exception:
            continue

    if not matches:
        return f"I don't have anything saved about that."

    # Pass raw matches to LLM for a natural language answer
    raw = "\n".join(matches[:15])
    return llm_tool.ask(
        f"The user asked: '{query}'\n\nRelevant memories:\n{raw}\n\nAnswer the question naturally.",
        system=RECALL_SYSTEM,
        temperature=0.2,
        max_tokens=150,
    )


# ── Auto-inject for other agents ──────────────────────────────────────────────

def get_relevant_context(query: str, max_lines: int = 10) -> str:
    """
    Called by other agents before answering — returns relevant memories
    as a compact string to inject into their prompts.
    Returns empty string if nothing relevant found.
    """
    if not VAULT.exists():
        return ""

    query_lower = query.lower()
    matches = []

    for md_file in VAULT.rglob("*.md"):
        # Skip daily conversation files to keep context focused
        if "conversations" in str(md_file):
            continue
        try:
            text = md_file.read_text(encoding="utf-8")
            for line in text.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if any(word in line.lower() for word in query_lower.split()
                       if len(word) > 3):
                    matches.append(line)
        except Exception:
            continue

    if not matches:
        return ""

    context = "\n".join(matches[:max_lines])
    return f"Relevant memories:\n{context}"


# ── Daily conversation summary ────────────────────────────────────────────────

def _summarise_conversation(messages: list) -> str:
    """Summarise a conversation and save it to the vault."""
    if not messages:
        return "[memory] No messages to summarise."

    conversation_text = "\n".join(
        f"{m.get('role', 'unknown').upper()}: {m.get('content', '')}"
        for m in messages
    )

    summary = llm_tool.ask(
        f"Extract key facts from this conversation worth remembering:\n\n{conversation_text}",
        system=SUMMARISE_SYSTEM,
        temperature=0.2,
        max_tokens=400,
    )

    today = datetime.datetime.now().strftime("%Y-%m-%d")
    target = VAULT / "conversations" / f"{today}.md"
    target.parent.mkdir(parents=True, exist_ok=True)

    content = f"# Conversation — {today}\n\n{summary}\n"
    if target.exists():
        with open(target, "a") as f:
            f.write(f"\n---\n\n{summary}\n")
    else:
        target.write_text(content)

    return f"[memory] Saved conversation summary to {target.name}"
