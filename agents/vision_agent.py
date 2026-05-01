# vision_agent.py
# Monitors the Bambu printer camera feed.
# Will use OpenCV to grab frames and YOLO to detect print issues
# (spaghetti, layer shifts, bed adhesion failures).
#
# Uses the FAST model (3B) — vision tasks need speed, not deep reasoning.
# The heavy lifting is done by YOLO, not the LLM.
#
# Status: Not yet implemented — camera integration = future phase.

from tools.llm_tool import FAST_MODEL  # noqa: F401 — imported so model is ready to use

# When camera is connected, these will be the real imports:
# import cv2
# from ultralytics import YOLO


def run(command: dict) -> str:
    """
    Inspect the Bambu printer camera feed and report what's happening.

    Expected command keys: (none required for basic check)

    Returns a status string describing the print status.
    """
    # TODO (camera phase):
    #   1. Connect to Bambu camera stream via RTSP or local IP
    #   2. Grab a frame with OpenCV
    #   3. Run YOLO to detect spaghetti / failures
    #   4. Return a plain-English description of what's happening

    print(f"[vision_agent] Camera monitoring not yet connected.")
    return "Printer camera monitoring is ready to implement once the camera stream is set up."
