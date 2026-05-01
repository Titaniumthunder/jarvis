# llm_tool.py
# Shared LLM helper for all Jarvis agents.
#
# Primary: Groq (Llama 3.3 70B) — free, fast, smart
# Fallback: local Ollama (Gemma4) — if Groq is unavailable
#
# All agents import ask() from here — swapping the backend is a one-line change.

import requests
import base64
import pathlib

OLLAMA_URL  = "http://localhost:11434/api/generate"
FAST_MODEL  = "llama-3.3-70b-versatile"
SMART_MODEL = "llama-3.3-70b-versatile"


def ask(
    prompt: str,
    system: str = "",
    model: str = SMART_MODEL,
    temperature: float = 0.3,
    max_tokens: int = 1000,
    expect_json: bool = False,
) -> str:
    """
    Send a prompt to Groq (with Ollama fallback) and return the response.
    Same signature as before — all agents work without changes.
    """
    try:
        from tools.groq_tool import ask as groq_ask
        return groq_ask(
            prompt=prompt,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
            expect_json=expect_json,
        )
    except Exception as e:
        print(f"[llm_tool] Groq failed: {e} — trying Ollama")

    # Ollama fallback
    full_prompt = f"{system}\n\n{prompt}".strip() if system else prompt
    payload = {
        "model": "gemma4:latest",
        "prompt": full_prompt,
        "stream": False,
        "options": {"temperature": temperature, "num_predict": max_tokens},
    }
    if expect_json:
        payload["format"] = "json"

    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=180)
        response.raise_for_status()
        return response.json().get("response", "").strip()
    except requests.exceptions.ConnectionError:
        return "[llm_tool] ERROR: Ollama is not running. Start it with: ollama serve"
    except requests.exceptions.Timeout:
        return "[llm_tool] ERROR: Ollama timed out."
    except Exception as e:
        return f"[llm_tool] ERROR: {e}"


def ask_with_image(
    prompt: str,
    image_path: str,
    system: str = "",
    model: str = SMART_MODEL,
    temperature: float = 0.2,
    max_tokens: int = 2000,
) -> str:
    """
    Send a prompt + image to Ollama (vision/multimodal).
    Gemma4 supports image input — pass the image as base64.

    Args:
        prompt:     The question or instruction.
        image_path: Path to a PNG/JPG image file.
        system:     Optional system prompt.
        model:      Must be a vision-capable model (gemma4:latest supports images).
        temperature, max_tokens: Same as ask().

    Returns:
        The model's response as a plain string.
    """
    # Read and base64-encode the image
    img = pathlib.Path(image_path)
    if not img.exists():
        return f"[llm_tool] ERROR: Image not found at {image_path}"

    image_b64 = base64.b64encode(img.read_bytes()).decode("utf-8")

    full_prompt = f"{system}\n\n{prompt}".strip() if system else prompt

    payload = {
        "model": model,
        "prompt": full_prompt,
        "images": [image_b64],   # Ollama multimodal field
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        }
    }

    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=180)
        response.raise_for_status()
        return response.json().get("response", "").strip()

    except requests.exceptions.ConnectionError:
        return "[llm_tool] ERROR: Ollama is not running. Start it with: ollama serve"
    except requests.exceptions.Timeout:
        return "[llm_tool] ERROR: Ollama timed out."
    except Exception as e:
        return f"[llm_tool] ERROR: {e}"
