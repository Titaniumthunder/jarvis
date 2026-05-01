# search_tool.py
# Web search using Brave Search API.
#
# Uses the Brave Answers API — returns a pre-summarised answer + sources.
# No scraping, no Ollama needed for search — Brave handles it all.
#
# Two modes:
#   search_and_summarise() → Brave Answers API → ready answer + citations
#   open_in_browser()      → opens the search in Chrome

import os
import subprocess
import urllib.parse
import urllib.request
import json

BRAVE_API_KEY = os.environ.get("BRAVE_API_KEY")
if not BRAVE_API_KEY:
    raise RuntimeError("BRAVE_API_KEY not set. Add it to .env or your shell.")

BRAVE_SEARCH_URL  = "https://api.search.brave.com/res/v1/web/search"
BRAVE_ANSWERS_URL = "https://api.search.brave.com/res/v1/summarizer/search"
MAX_RESULTS = 5


def search_and_summarise(query: str) -> str:
    """
    Use Brave Search API to get results, then summarise with Ollama.
    Returns "ANSWER|||SOURCES" format for the server to split.
    """
    from tools import llm_tool
    print(f"[search_tool] Brave search: '{query}'")

    results, _ = _brave_search(query)

    if not results:
        return "I couldn't find any results for that.|||"

    # Build compact context from Brave snippets (already high quality)
    context = "\n\n".join(
        f"- {r['title']}: {r['description']}"
        for r in results[:5]
        if r.get("description")
    )

    prompt = (
        f"Answer this question in 2-4 sentences using only the search results below.\n"
        f"Question: {query}\n\n"
        f"Search results:\n{context}\n\n"
        f"Be direct and specific. Include names, dates, or facts from the results."
    )

    print(f"[search_tool] Summarising with Ollama ({len(prompt)} chars)...")
    answer = llm_tool.ask(prompt=prompt, temperature=0.1, max_tokens=300)

    if not answer or answer.startswith("[llm_tool]"):
        # Fallback: just return the top snippet directly
        answer = results[0].get("description", "Couldn't summarise results.")

    sources = "\n".join(
        f"  • {r['title']}: {r['url']}"
        for r in results[:3]
        if r.get("title") and r.get("url")
    )

    print(f"[search_tool] Done.")
    return f"{answer}|||{sources}"


def open_in_browser(query: str, browser: str = "chrome") -> str:
    """Open a Google search for `query` in the specified browser."""
    url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
    browser_map = {
        "chrome":  "Google Chrome",
        "safari":  "Safari",
        "firefox": "Firefox",
    }
    app_name = browser_map.get(browser.lower(), "Google Chrome")
    print(f"[search_tool] Opening '{query}' in {app_name}")
    subprocess.Popen(["open", "-a", app_name, url])
    return f"Opened '{query}' in {app_name}."


# ── Brave API helpers ─────────────────────────────────────────────────────────

def _brave_search(query: str) -> tuple:
    """
    Call Brave web search. Returns (results_list, summary_key).
    summary_key is used to fetch the AI-generated answer in a second call.
    """
    params = urllib.parse.urlencode({
        "q": query,
        "count": MAX_RESULTS,
        "summary": 1,           # request AI summary
        "extra_snippets": 1,    # richer snippets
    })
    url = f"{BRAVE_SEARCH_URL}?{params}"

    try:
        req = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "X-Subscription-Token": BRAVE_API_KEY,
            }
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            # Handle gzip
            import gzip
            raw = resp.read()
            try:
                data = json.loads(gzip.decompress(raw))
            except Exception:
                data = json.loads(raw)

        # Extract web results
        results = []
        for item in data.get("web", {}).get("results", []):
            results.append({
                "title":       item.get("title", ""),
                "url":         item.get("url", ""),
                "description": item.get("description", "") or item.get("extra_snippets", [""])[0],
            })

        # Extract summary key for the answers endpoint
        summary_key = data.get("summarizer", {}).get("key", "")

        return results, summary_key

    except Exception as e:
        print(f"[search_tool] Brave search failed: {e}")
        return [], ""


def _brave_answer(summary_key: str) -> str:
    """
    Fetch the AI-generated answer from Brave using the summary key.
    """
    params = urllib.parse.urlencode({
        "key": summary_key,
        "entity_info": 1,
    })
    url = f"{BRAVE_ANSWERS_URL}?{params}"

    try:
        req = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "X-Subscription-Token": BRAVE_API_KEY,
            }
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            import gzip
            raw = resp.read()
            try:
                data = json.loads(gzip.decompress(raw))
            except Exception:
                data = json.loads(raw)

        # Extract answer text from summary segments
        segments = data.get("summary", [])
        if segments:
            answer = " ".join(
                seg.get("data", "")
                for seg in segments
                if seg.get("type") == "token"
            ).strip()
            if answer:
                return answer

        # Fallback: top-level answer field
        return data.get("answer", {}).get("text", "")

    except Exception as e:
        print(f"[search_tool] Brave answers failed: {e}")
        return ""
