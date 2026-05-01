# tests/test_brain.py
# Interactive test loop for brain.py — no mic required.
#
# This lets you type commands directly and see exactly what Ollama returns
# before wiring up the microphone. Great for checking that:
#   1. Ollama is running and responding
#   2. Llama 3 returns valid JSON
#   3. The action library covers your commands
#
# Usage:
#   cd jarvis
#   python tests/test_brain.py
#
# Prerequisites:
#   - Ollama is running:  ollama serve
#   - Llama 3 is pulled:  ollama pull llama3

import sys
import os

# Add the parent directory to the path so we can import brain.py
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import brain

# ── Test commands that cover every action in the library ─────────────────────
EXAMPLE_COMMANDS = [
    "What time is it?",
    "Find all Python files in my project",
    "Pick up the red block",
    "Design a small box 5 cm wide",
    "What is in my project folder?",
    "Check the printer camera",
    "Open a new terminal window",
    "This is a totally unknown command xyz",
]


def run_interactive():
    """Let the user type commands and see the brain's response in real time."""
    print("=" * 60)
    print("  Jarvis Brain Test — type commands, see JSON responses")
    print("  Type 'examples' to run all built-in test commands")
    print("  Type 'quit' to exit")
    print("=" * 60)
    print()

    while True:
        try:
            user_input = input("Command: ").strip()
        except KeyboardInterrupt:
            print("\nBye.")
            break

        if not user_input:
            continue

        if user_input.lower() in ("quit", "exit", "q"):
            print("Bye.")
            break

        if user_input.lower() == "examples":
            run_examples()
            continue

        _test_command(user_input)


def run_examples():
    """Run every example command and print a summary."""
    print("\n── Running all example commands ──")
    passed = 0
    failed = 0

    for cmd in EXAMPLE_COMMANDS:
        print(f"\nInput:  {cmd}")
        result = brain.ask(cmd)
        action = result.get("action", "MISSING")
        reply  = result.get("reply", "MISSING")

        ok = (
            action in brain.KNOWN_ACTIONS and
            "agent" in result and
            "params" in result and
            "reply" in result
        )

        status = "PASS" if ok else "FAIL"
        if ok:
            passed += 1
        else:
            failed += 1

        print(f"Action: {action}")
        print(f"Reply:  {reply}")
        print(f"Status: {status}")

    print(f"\n── Results: {passed} passed, {failed} failed ──\n")


def _test_command(text: str):
    """Send a single command to the brain and pretty-print the result."""
    import json

    print(f"\nSending: '{text}'")
    print("-" * 40)
    result = brain.ask(text)
    print(json.dumps(result, indent=2))
    print()


if __name__ == "__main__":
    if "--examples" in sys.argv:
        run_examples()
    else:
        run_interactive()
