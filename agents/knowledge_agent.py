# knowledge_agent.py
# Answers questions in a smart three-tier system:
#
#   1. Meta questions about Jarvis  → instant hardcoded capabilities answer
#   2. General knowledge            → ask LLM directly (it already knows)
#   3. LLM doesn't know             → fall back to Google web search
#
# File-reading (the old approach) is no longer the default — the LLM's built-in
# knowledge covers 99% of general questions faster and better than scanning files.

from tools import llm_tool
from tools.llm_tool import SMART_MODEL
from agents import memory_agent

GENERAL_KNOWLEDGE_SYSTEM = """
You are Jarvis, a knowledgeable assistant. Answer the user's question from your own knowledge.

Match response length to the question:
- Simple or factual → 1-2 sentences max
- Moderate → 2-4 sentences
- Complex / technical → use short bullet points

Never pad with filler. Be direct. Don't repeat the question. Don't say "Great question!".
If you truly don't know or it requires real-time data, respond with exactly: SEARCH_NEEDED
""".strip()

# Keywords that mean the user is asking about Jarvis's own capabilities
_META_KEYWORDS = {
    "what can you do", "what tasks", "your capabilities", "what are you able",
    "what do you do", "help me with", "what can jarvis", "what can i ask",
    "what commands", "list your", "show your", "tell me what you can",
}

# Phrases that mean the LLM doesn't know → trigger web search fallback
_UNCERTAIN_PHRASES = [
    "search_needed", "i don't know", "i do not know", "i'm not sure",
    "i cannot answer", "i don't have information", "i do not have",
    "as of my knowledge cutoff", "i'm unable to", "no information available",
    "i cannot provide", "beyond my knowledge",
]

CAPABILITIES_ANSWER = """Here's what I can do for you:

• **Time** — "What time is it?"
• **Web search** — "Search for best 3D printers 2025"
• **Open in browser** — "Open latest iPhone reviews in Chrome"
• **File browsing** — "What's in my Personal Project folder?"
• **Run commands** — "Run ls in my downloads folder"
• **Generate image** — "Generate an image of a sunset"
• **3D preview** — "Design a curved vase" (rotatable browser preview)
• **Blender model** — "Generate a vase in Blender"
• **Shap-E 3D** — "Generate a dragon using Shap-E" (AI organic mesh)
• **Clarify** — If I'm not sure what you mean, I'll ask

Just talk to me naturally — I'll figure out the right action."""


def run(command: dict) -> str:
    """
    Answer a question using a three-tier fallback:
      1. Meta/capability questions → instant answer
      2. General knowledge         → LLM from its own training
      3. LLM unsure                → Google web search

    Expected command keys:
        question (str): the question to answer
    """
    question = command.get("question", "")
    if not question:
        return "No question provided."

    # ── Tier 1: Meta questions about Jarvis ───────────────────────────────────
    q_lower = question.lower()
    if any(kw in q_lower for kw in _META_KEYWORDS):
        return CAPABILITIES_ANSWER

    # ── Tier 1.5: Check memory vault for relevant context ─────────────────────
    memory_context = memory_agent.get_relevant_context(question)
    system = GENERAL_KNOWLEDGE_SYSTEM
    if memory_context:
        system = f"{GENERAL_KNOWLEDGE_SYSTEM}\n\n{memory_context}"
        print(f"[knowledge_agent] Injecting memory context")

    # ── Tier 2: Ask the LLM from its own knowledge ────────────────────────────
    print(f"[knowledge_agent] Answering from LLM knowledge: '{question}'")
    answer = llm_tool.ask(
        prompt=question,
        system=system,
        model=SMART_MODEL,
        temperature=0.2,
        max_tokens=400,
    )

    # ── Tier 3: LLM doesn't know → fall back to web search ───────────────────
    if _seems_uncertain(answer):
        print(f"[knowledge_agent] LLM uncertain — falling back to web search")
        from tools import search_tool
        return search_tool.search_and_summarise(question)

    return answer


def _seems_uncertain(answer: str) -> bool:
    """Return True if the LLM's answer signals it doesn't know."""
    lower = answer.lower().strip()
    return any(phrase in lower for phrase in _UNCERTAIN_PHRASES)
