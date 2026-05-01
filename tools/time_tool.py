# time_tool.py
# Returns the current date and time as a string

from datetime import datetime

def get_current_time() -> str:
    """Returns a human-readable current datetime string."""
    return datetime.now().strftime("It's %A, %B %d %Y at %I:%M %p")
