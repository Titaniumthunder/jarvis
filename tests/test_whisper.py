# tests/test_whisper.py
# Quick smoke test for Whisper — records 5 seconds from the mic and prints
# the transcription. No brain, no agents. Just mic → text.
#
# Usage:
#   cd jarvis
#   python tests/test_whisper.py
#
# If this works, listen.py will work.

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from listen import record_and_transcribe

print("Testing Whisper microphone input...")
print("Speak for 5 seconds after 'Recording...' appears.\n")

text = record_and_transcribe()

if text:
    print(f"\nTranscription result: '{text}'")
    print("\nWhisper test PASSED.")
else:
    print("\nNothing transcribed — check your mic permissions in System Settings.")
    print("Whisper test FAILED.")
