# tts_tool.py
# Text-to-speech using macOS's built-in `say` command.
# No install required — works on any Mac out of the box.
#
# To change the voice, run `say -v ?` in terminal to list all available voices.
# Good options: Samantha (default), Alex, Tom, Daniel (British)

import subprocess

VOICE = "Samantha"   # change this to any voice from `say -v ?`
RATE  = 200          # words per minute — default is ~175, higher = faster


def speak(text: str) -> None:
    """
    Speak the given text aloud using the macOS `say` command.
    Runs synchronously — Jarvis waits for speech to finish before continuing.

    Args:
        text: The string to speak aloud.
    """
    if not text or not text.strip():
        return

    # Clean up the text a bit — remove newlines so it sounds natural
    clean = text.replace("\n", ". ").strip()

    subprocess.run(
        ["say", "-v", VOICE, "-r", str(RATE), clean],
        check=False   # don't crash if say fails for any reason
    )
