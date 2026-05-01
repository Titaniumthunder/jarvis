# gemini_tool.py
# Google Gemini API helper — drop-in replacement for llm_tool.py calls.
#
# Used for:
#   - Brain (command routing) — Gemini 2.0 Flash is smarter + faster than Gemma4
#   - Agent calls (knowledge, memory, search summarisation)
#
# Falls back to Ollama if Gemini is unavailable.

import os

from google import genai
from google.genai import types

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY not set. Add it to .env or your shell.")

FAST_MODEL      = "gemini-2.0-flash"   # brain + simple tasks — 1500 req/day free
SMART_MODEL     = "gemini-2.0-flash"   # agents — same model, plenty fast

_client = None

def _get_client():
    global _client
    if _client is None:
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


def ask(
    prompt: str,
    system: str = "",
    model: str = SMART_MODEL,
    temperature: float = 0.3,
    max_tokens: int = 1000,
    expect_json: bool = False,
) -> str:
    """
    Send a prompt to Gemini and return the response as a plain string.
    Same signature as llm_tool.ask() so it can be swapped in anywhere.
    """
    client = _get_client()

    full_prompt = f"{system}\n\n{prompt}".strip() if system else prompt

    config = types.GenerateContentConfig(
        temperature=temperature,
        max_output_tokens=max_tokens,
        response_mime_type="application/json" if expect_json else "text/plain",
    )

    try:
        response = client.models.generate_content(
            model=model,
            contents=full_prompt,
            config=config,
        )
        return response.text.strip()

    except Exception as e:
        err = str(e)
        print(f"[gemini_tool] ERROR: {err[:200]}")
        raise  # let caller (llm_tool or brain) handle the fallback


def ask_json(prompt: str, system: str = "", temperature: float = 0.2) -> str:
    """Convenience wrapper that requests JSON output."""
    return ask(prompt, system=system, temperature=temperature, expect_json=True)
