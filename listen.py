# listen.py
# Handles microphone input and transcribes speech to text using Whisper.
#
# How it works:
#   1. Records audio from your Mac's default mic for a fixed number of seconds
#   2. Saves it to a temporary WAV file
#   3. Feeds the WAV to Whisper (running locally)
#   4. Returns the transcribed text string
#
# For Phase 3 testing you don't need to call this — use test_brain.py instead.

import os
import wave
import tempfile
import pyaudio     # pip install pyaudio — records from the mic
import whisper     # pip install openai-whisper — local transcription, no API needed

# ── Recording config ──────────────────────────────────────────────────────────
SAMPLE_RATE    = 16000   # 16kHz — Whisper's expected sample rate
CHANNELS       = 1       # mono
CHUNK          = 1024    # number of audio frames per buffer
RECORD_SECONDS = 5       # how long to listen before transcribing

# ── Whisper model ─────────────────────────────────────────────────────────────
# "base" is fast and accurate enough for commands on an M5 Pro.
# Options from smallest/fastest to largest/most accurate:
#   tiny, base, small, medium, large
# The model downloads automatically the first time (~140MB for base).
WHISPER_MODEL = "base"

# Load the model once at startup (not on every call — it's slow to load)
print("[listen] Loading Whisper model... (first run downloads ~140MB)")
_model = whisper.load_model(WHISPER_MODEL)
print(f"[listen] Whisper '{WHISPER_MODEL}' model ready.")


def record_and_transcribe() -> str:
    """
    Record audio from the mic for RECORD_SECONDS seconds, then transcribe it.

    Returns:
        The transcribed text as a string (stripped of leading/trailing whitespace).
        Returns empty string "" if nothing was heard or transcription failed.
    """
    audio_data = _record_audio()
    if not audio_data:
        return ""
    return _transcribe(audio_data)


def _record_audio() -> bytes | None:
    """
    Open the mic and record raw audio bytes for RECORD_SECONDS.
    Returns raw PCM bytes, or None on error.
    """
    pa = pyaudio.PyAudio()

    try:
        stream = pa.open(
            format=pyaudio.paInt16,   # 16-bit audio
            channels=CHANNELS,
            rate=SAMPLE_RATE,
            input=True,
            frames_per_buffer=CHUNK
        )

        print(f"[listen] Recording for {RECORD_SECONDS}s... speak now")
        frames = []
        for _ in range(0, int(SAMPLE_RATE / CHUNK * RECORD_SECONDS)):
            frames.append(stream.read(CHUNK, exception_on_overflow=False))

        stream.stop_stream()
        stream.close()
        print("[listen] Done recording.")
        return b"".join(frames)

    except Exception as e:
        print(f"[listen] Mic error: {e}")
        return None
    finally:
        pa.terminate()


def _transcribe(audio_bytes: bytes) -> str:
    """
    Write audio bytes to a temp WAV file and run Whisper on it.
    Returns the transcribed text string.
    """
    # Write to a temporary file — Whisper needs a file path, not raw bytes
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name
        _write_wav(tmp_path, audio_bytes)

    try:
        result = _model.transcribe(tmp_path, language="en", fp16=False)
        text = result["text"].strip()
        print(f"[listen] Heard: '{text}'")
        return text
    except Exception as e:
        print(f"[listen] Transcription error: {e}")
        return ""
    finally:
        os.remove(tmp_path)   # clean up the temp file


def _write_wav(path: str, audio_bytes: bytes) -> None:
    """Write raw PCM bytes to a proper WAV file that Whisper can read."""
    with wave.open(path, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)          # 2 bytes = 16-bit
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio_bytes)
