# main.py
# Entry point for Jarvis — ties together listening, thinking, and acting.
#
# Run modes:
#   python main.py           → full voice mode (mic → Whisper → brain → agents)
#   python main.py --text    → text mode for testing without mic
#   python main.py --silent  → text mode with no spoken output (faster for debugging)

import sys
import brain
import orchestrator
from tools import tts_tool

# Set to False if you want to skip spoken output (e.g. late at night)
SPEAK_REPLIES = "--silent" not in sys.argv


def voice_loop():
    """Continuously listen for voice commands and act on them."""
    import listen  # only imported here so text mode doesn't load Whisper

    print("[main] Jarvis is listening. Press Ctrl+C to stop.")
    _speak("Jarvis online. Ready for your command.")
    while True:
        try:
            text = listen.record_and_transcribe()
            if not text:
                print("[main] Nothing heard, listening again...")
                continue
            _handle(text)
        except KeyboardInterrupt:
            print("\n[main] Shutting down.")
            _speak("Shutting down. Goodbye.")
            break


def text_loop():
    """Accept typed commands — useful for testing without the mic."""
    print("[main] Jarvis text mode. Type your command (or 'quit' to exit).")
    _speak("Jarvis text mode active.")
    while True:
        try:
            text = input("\nYou: ").strip()
            if not text:
                continue
            if text.lower() in ("quit", "exit", "q"):
                _speak("Goodbye.")
                print("Bye.")
                break
            _handle(text)
        except KeyboardInterrupt:
            print("\nBye.")
            break


def _handle(text: str, _depth: int = 0):
    """
    Send a command through the brain, dispatch to the right agent, speak the result.
    If the brain asks for clarification, prompt the user and retry once with the full context.
    _depth prevents infinite clarification loops (max 2 rounds).
    """
    response = brain.ask(text)
    action   = response.get("action", "unknown")

    # ── Clarification loop ────────────────────────────────────────────────────
    if action == "clarify" and _depth < 2:
        params     = response.get("params", {})
        question   = params.get("question", response.get("reply", "Could you clarify?"))
        best_guess = params.get("best_guess", "").strip()

        print(f"\nJarvis: {question}\n")
        _speak(question)

        try:
            if "--text" in sys.argv:
                clarification = input("You: ").strip()
            else:
                import listen
                clarification = listen.record_and_transcribe()

            if not clarification:
                print("[main] No clarification received.")
                return

            # If Jarvis made a best guess and user confirmed with yes/yep/yeah/correct
            YES_WORDS = {"yes", "yeah", "yep", "yup", "correct", "right", "exactly", "sure", "ok", "okay"}
            if best_guess and clarification.lower().strip(" .!?") in YES_WORDS:
                # User confirmed the best guess — re-run with the corrected command
                corrected = text.lower().replace(
                    text.split()[-1],  # replace last word (the misheard part)
                    best_guess
                ) if best_guess else text
                print(f"[main] Confirmed: running with '{corrected}'")
                _handle(corrected, _depth=_depth + 1)
            else:
                # User gave a real clarification — combine with original intent
                combined = f"{text}. To clarify: {clarification}"
                _handle(combined, _depth=_depth + 1)

        except Exception as e:
            print(f"[main] Clarification error: {e}")
        return

    # ── Normal response ───────────────────────────────────────────────────────
    result = orchestrator.dispatch(response)
    print(f"\nJarvis: {result}\n")
    _speak(result)


def _speak(text: str):
    """Speak text aloud — does nothing if --silent flag is set."""
    if SPEAK_REPLIES:
        tts_tool.speak(text)


if __name__ == "__main__":
    if "--text" in sys.argv:
        text_loop()
    else:
        voice_loop()
