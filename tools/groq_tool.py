# groq_tool.py
# Groq API helper — fast cloud LLM, completely free, no credit card.
#
# Model: Llama 3.3 70B — smarter than local Gemma4, ~500 tok/sec on Groq's chips
# Free limits: 14,400 requests/day, 500,000 tokens/day — more than enough
#
# Falls back to local Ollama (Gemma4) if Groq is unavailable.

from groq import Groq

import os
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY not set. Add it to .env or your shell.")
FAST_MODEL   = "llama-3.3-70b-versatile"
SMART_MODEL  = "llama-3.3-70b-versatile"

_client = None

def _get_client() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=GROQ_API_KEY)
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
    Send a prompt to Groq and return the response as a plain string.
    Same signature as llm_tool.ask() — drop-in replacement.
    """
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    kwargs = dict(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    if expect_json:
        kwargs["response_format"] = {"type": "json_object"}

    client = _get_client()
    response = client.chat.completions.create(**kwargs)
    return response.choices[0].message.content.strip()


def ask_json(prompt: str, system: str = "", temperature: float = 0.1) -> str:
    """Convenience wrapper that requests JSON output."""
    return ask(prompt, system=system, temperature=temperature, expect_json=True)
