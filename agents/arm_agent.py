# arm_agent.py
# Controls the robot arm via:
#   YOLO (finds the object on camera) →
#   coordinate calculation →
#   serial commands → Arduino → PCA9685 → servos
#
# Uses the FAST model (3B) for any LLM calls because arm commands are
# simple and speed matters more than deep reasoning here.
#
# Status: Not yet implemented — hardware not purchased.
# Wired to llm_tool with FAST_MODEL so it's ready when hardware arrives.

from tools.llm_tool import FAST_MODEL  # noqa: F401 — imported so model is ready to use

# When hardware is connected, these will be the real imports:
# import serial
# from ultralytics import YOLO


def run(command: dict) -> str:
    """
    Move the arm to pick up or interact with a target object.

    Expected command keys:
        target_object (str): what to pick up (e.g. "red block")
        motion        (str): what to do   (e.g. "pick_up", "place", "point_at")

    Returns a status string.
    """
    target = command.get("target_object", "unknown object")
    motion = command.get("motion", "unknown motion")

    # TODO (hardware phase):
    #   1. Capture frame from camera
    #   2. Run YOLO to find `target` bounding box
    #   3. Convert pixel coords → servo angles
    #   4. Send angles over serial to Arduino
    #   5. Return success/failure

    print(f"[arm_agent] Would perform '{motion}' on '{target}' — hardware not connected yet.")
    return f"Arm action '{motion}' on '{target}' is ready to implement once hardware arrives."
