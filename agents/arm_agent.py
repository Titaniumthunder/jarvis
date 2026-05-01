# arm_agent.py
# Drives the simulated Franka Panda arm via tools.arm_sim_client.
#
# YOLO + camera input is not wired up yet, so target_object → world coords
# uses a hardcoded lookup table for now. When perception lands, replace
# TARGETS with a vision-based resolver and the rest of this file stays the same.

from tools import arm_sim_client

# Workspace coordinates (Franka base frame, metres).
TARGETS = {
    "red block":   [0.5,  0.0, 0.1],
    "blue block":  [0.5,  0.2, 0.1],
    "green block": [0.5, -0.2, 0.1],
    "home":        [0.3,  0.0, 0.5],
}

APPROACH_HEIGHT = 0.15  # metres above the target for the pre-grasp pose


def run(command: dict) -> str:
    target_name = command.get("target_object", "").strip().lower()
    motion = command.get("motion", "").strip().lower()

    if not arm_sim_client.ensure_running():
        return "Could not start the arm simulator. See docs/ARM_SETUP.md."

    if target_name not in TARGETS:
        known = ", ".join(sorted(TARGETS))
        return f"I don't know where '{target_name}' is. Known targets: {known}."

    target = TARGETS[target_name]

    if motion == "pick_up":
        return _pick_up(target_name, target)
    if motion == "place":
        return _place(target_name, target)
    if motion == "point_at":
        return _point_at(target_name, target)
    if motion in ("home", ""):
        result = arm_sim_client.home()
        return _format(f"Moved arm to home pose.", result)

    return f"Unknown motion '{motion}'. Try pick_up, place, point_at, or home."


# ─── Motions ──────────────────────────────────────────────────────────────────

def _pick_up(name: str, target) -> str:
    above = [target[0], target[1], target[2] + APPROACH_HEIGHT]
    steps = [
        ("open gripper", lambda: arm_sim_client.open_gripper()),
        (f"approach above {name}", lambda: arm_sim_client.move_to(above)),
        (f"descend onto {name}", lambda: arm_sim_client.move_to(target)),
        ("close gripper", lambda: arm_sim_client.close_gripper()),
        (f"lift {name}", lambda: arm_sim_client.move_to(above)),
    ]
    return _run_sequence(f"Picked up {name}.", steps)


def _place(name: str, target) -> str:
    above = [target[0], target[1], target[2] + APPROACH_HEIGHT]
    steps = [
        (f"approach drop point at {name}", lambda: arm_sim_client.move_to(above)),
        (f"lower onto {name}", lambda: arm_sim_client.move_to(target)),
        ("open gripper", lambda: arm_sim_client.open_gripper()),
        (f"retreat from {name}", lambda: arm_sim_client.move_to(above)),
    ]
    return _run_sequence(f"Placed object at {name}.", steps)


def _point_at(name: str, target) -> str:
    result = arm_sim_client.move_to(target)
    return _format(f"Pointing at {name}.", result)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _run_sequence(success_msg: str, steps) -> str:
    for label, action in steps:
        result = action()
        if result.get("status") != "success":
            return f"Arm failed during '{label}': {result.get('message', result)}"
    return success_msg


def _format(success_msg: str, result: dict) -> str:
    if result.get("status") == "success":
        return success_msg
    return f"Arm error: {result.get('message', result)}"
